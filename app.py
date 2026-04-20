# app.py
import os, warnings, random, re, time, streamlit as st
import google.generativeai as genai
import fitz  # PyMuPDF
from PIL import Image

warnings.simplefilter('ignore', FutureWarning)
os.environ['GRPC_VERBOSITY'] = 'NONE'
os.environ['GLOG_minloglevel'] = '3'

from languages import translations, affiliate_links
from utils import generate_content_with_retry, add_to_history, CUSTOM_CSS
from mock_exam_engine import ExamEngine

st.set_page_config(page_title="Catalyst AI", page_icon="🔬", layout="wide")
st.markdown(CUSTOM_CSS, unsafe_allow_html=True)

# --- セッション初期化 ---
init_keys = {
    "pdf_texts": {}, "history": [], "viewing_history": None, "uploader_key": 0,
    "available_models": [], "test_result_obj": None, "solve_feedback": None,
    "current_mode": None, "current_affiliate": None, "pdf_images": {} 
}
for k, v in init_keys.items():
    if k not in st.session_state: st.session_state[k] = v

language = st.sidebar.selectbox("Language / 言語", list(translations.keys()))
t = translations.get(language, translations["Japanese"])

if not st.session_state.current_affiliate:
    st.session_state.current_affiliate = random.choice(affiliate_links["Japanese"])

def on_mode_change():
    st.session_state.test_result_obj = None
    st.session_state.solve_feedback = None
    st.session_state.viewing_history = None
    st.session_state.uploader_key += 1
    st.session_state.current_affiliate = random.choice(affiliate_links["Japanese"])

# --- サイドバー・モード管理 ---
with st.sidebar:
    app_mode = st.radio(
        t["sidebar_mode_label"], 
        [t["mode_research"], t["mode_test"]],
        on_change=on_mode_change
    )

    st.markdown("---")
    st.markdown("### 🔑 システム稼働状況")
    
    active_api_key = None
    has_secret_key = False
    
    try:
        if "ADMIN_API_KEY" in st.secrets:
            active_api_key = str(st.secrets["ADMIN_API_KEY"]).strip()
            has_secret_key = True
    except Exception:
        pass 

    if has_secret_key and active_api_key:
        st.success("🟢 AIサーバー接続済み (Pro稼働中)")
    else:
        st.warning("サーバーにAPIキーが設定されていません。")
        user_api_key = st.text_input("ご自身のGemini APIキーを入力してください", type="password")
        if user_api_key:
            active_api_key = user_api_key.strip()

    selected_model_name = "gemini-3.0-flash" 
    if active_api_key:
        if not active_api_key.isascii():
            st.error("🚨 APIキーに不正な文字が含まれています。半角英数字のみで設定してください。")
            st.stop()

        try:
            genai.configure(api_key=active_api_key, transport='rest')
            if not st.session_state.available_models:
                raw_models = [m.name for m in genai.list_models() if 'generateContent' in m.supported_generation_methods]
                advanced_models = [m for m in raw_models if not re.search(r'gemini-[12]\.', m)]
                if not advanced_models:
                    advanced_models = ["models/gemini-3.1-pro", "models/gemini-3.0-pro", "models/gemini-3.0-flash"]
                st.session_state.available_models = advanced_models
                
            if st.session_state.available_models:
                selected_model_name = st.selectbox(t["model_label"], st.session_state.available_models)
        except Exception as e:
            st.error(f"🚨 API連携エラー: {e}")

    st.markdown("---")
    st.markdown("### 🌐 外部サポート")
    st.markdown("👉 [DeepL翻訳を開く](https://www.deepl.com/translator)")

    st.markdown("---")
    if st.button(t["new_create_btn"], type="primary"):
        on_mode_change()
        st.session_state.pdf_texts = {} 
        st.session_state.pdf_images = {}
        st.rerun()

    st.markdown("---")
    st.subheader(t["history_title"])
    if not st.session_state.history:
        st.caption(t["history_empty"])
    else:
        for i, item in enumerate(reversed(st.session_state.history)):
            with st.expander(f"{item['time']} : {item['type']}"):
                c1, c2 = st.columns(2)
                if c1.button(t["history_load"], key=f"h_l_{i}"):
                    st.session_state.viewing_history = item
                    st.rerun()
                if c2.button(t["history_del"], key=f"h_d_{i}"):
                    idx = len(st.session_state.history) - 1 - i
                    st.session_state.history.pop(idx)
                    st.rerun()

# --- メインエリア ---
st.title(t["title"])

if st.session_state.viewing_history:
    st.markdown(st.session_state.viewing_history['content'], unsafe_allow_html=True)
    if st.button(t["close_view"]):
        st.session_state.viewing_history = None
        st.rerun()

elif active_api_key:
    st.subheader(t["header_upload"])
    c1, c2 = st.columns(2)
    with c1:
        ufs = st.file_uploader(t["upload_pdf"], type="pdf", accept_multiple_files=True, key=f"up_{st.session_state.uploader_key}_{app_mode}")
        if ufs:
            for f in ufs:
                if f.name not in st.session_state.pdf_texts:
                    file_bytes = f.read()
                    pdf_doc = fitz.open(stream=file_bytes, filetype="pdf")
                    extracted_text = [f"【ページ {p_idx + 1}】\n{p.get_text()}" for p_idx, p in enumerate(pdf_doc)]
                    st.session_state.pdf_texts[f.name] = "\n".join(extracted_text)
                    images = []
                    for i in range(min(3, len(pdf_doc))):
                        pix = pdf_doc[i].get_pixmap(matrix=fitz.Matrix(2, 2))
                        img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
                        img.thumbnail((1024, 1024))
                        images.append(img)
                    st.session_state.pdf_images[f.name] = images

    with c2:
        u_img = st.file_uploader(t["upload_img"], type=["png", "jpg", "jpeg"], key=f"img_{st.session_state.uploader_key}_{app_mode}")

    # ==========================================
    # 🔬 1. 論文・資料解析
    # ==========================================
    if app_mode == t["mode_research"]:
        if not st.session_state.pdf_texts and not u_img:
            st.warning("👆 資料をアップロードしてください。")
        else:
            res_images = []
            if u_img:
                img_obj = Image.open(u_img)
                img_obj.thumbnail((1024, 1024))
                res_images.append(img_obj)
            if st.session_state.pdf_images:
                for imgs in st.session_state.pdf_images.values(): res_images.extend(imgs)
            txt = "\n".join(st.session_state.pdf_texts.values())[:15000]

            rtab1, rtab2, rtab3, rtab4 = st.tabs(["⚔️ 構造化要約", "📊 画像解析", "📚 引用ガイド", "💬 Q&A"])
            
            with rtab1:
                st.info("💡 日本語の指定フォーマットで詳細に解析します。")
                if st.button("📝 構造化要約を実行", key="btn_sum", type="primary"):
                    with st.spinner("日本語で執筆中..."):
                        # プロンプトから「英語」「翻訳」という言葉を完全に消去
                        prompt_sum = f"""
あなたは日本語のみを使用する専門の研究員です。
提示された資料の内容を精査し、必ず以下の「日本語の9つの見出し」に則って、一項目ずつ非常に詳しく日本語で記述してください。

## 📑 要旨
## 📝 本文の要約
## 🎯 目的
## 🔬 実験操作、方法
## 📊 結果
## 🤔 考察
## ✅ 結論
## 🚀 未来への展望、疑問
## 🔑 Keyワード、重要ポイント、用語

【ルール】
1. 返答は最初から最後まで「日本語」のみを使用すること。
2. 見出しの順番は絶対に変えないこと。
3. 抽象的な表現は避け、数値や具体的な事実を日本語で詳細に書くこと。

【資料内容】
{txt if txt else '（画像データを参照してください）'}
"""
                        try:
                            res = generate_content_with_retry(selected_model_name, res_images if res_images else None, prompt_sum)
                            st.markdown(res); add_to_history("構造化要約", res)
                        except Exception as e:
                            if "429" in str(e): st.error("⏳ 通信制限中です。1分待ってから再度お試しください。")
                            else: st.error(f"エラー: {e}")
            
            with rtab2:
                if u_img:
                    if st.button("🔍 画像単体を解析"):
                        with st.spinner("解析中..."):
                            res = generate_content_with_retry(selected_model_name, [Image.open(u_img)], "この画像の内容を詳しく日本語で解説してください。日本語以外の使用は禁止します。")
                            st.markdown(res); add_to_history("画像解析", res)
            
            with rtab3:
                if st.button("📚 執筆用 参考文献を探索"):
                    with st.spinner("実在する文献を日本語で提案中..."):
                        prompt_ref = f"""
以下の資料を補強するために引用すべき、実在の専門論文を3件、日本語で提案してください。
【条件】
- タイトル、著者、引用理由、すべて日本語で記述すること。
- 幻覚（存在しない論文）は厳禁。
{txt}
"""
                        res = generate_content_with_retry(selected_model_name, res_images if res_images else None, prompt_ref)
                        st.markdown(res); add_to_history("参考文献提案", res)
            
            with rtab4:
                q = st.text_input("質問を入力：")
                if st.button("💬 回答を生成") and q:
                    res = generate_content_with_retry(selected_model_name, res_images if res_images else None, f"資料に基づき、日本語で答えてください。：{q}\n資料：{txt}")
                    st.markdown(res); add_to_history("Q&A", res)

    # ==========================================
    # 🎓 2. テスト対策
    # ==========================================
    elif app_mode == t["mode_test"]:
        tab1, tab2, tab3, tab4 = st.tabs(["✍️ 問題作成", "🧠 AI添削", "📝 解答生成", "🔄 模試生成"])
        combined_text = "\n".join(st.session_state.pdf_texts.values())[:20000]
        image_payload = []
        if st.session_state.pdf_images:
            for imgs in st.session_state.pdf_images.values(): image_payload.extend(imgs)
        if u_img: image_payload.append(Image.open(u_img))
        
        with tab1:
            ca, cb = st.columns(2)
            with ca: 
                t_level = st.selectbox(t["test_level_label"], t["test_levels"])
                t_type = st.selectbox(t["test_type_label"], t["test_types"])
            with cb: diff = st.selectbox(t["test_diff_label"], t["test_diffs"])
            if st.button(t["test_btn"], type="primary"):
                with st.spinner("問題を作成中..."):
                    p = f"対象：{t_level}、難易度：{diff}。資料から日本語の問題と解説を作成してください。\n資料：{combined_text}"
                    res = generate_content_with_retry(selected_model_name, image_payload if image_payload else None, p)
                    st.write(res)

        with tab2:
            st.info("回答を入力して採点を受けられます。")
        with tab3:
            st.info("資料の正解を作成します。")
        with tab4:
            st.info("完全再現模試を作成します。")

else:
    st.warning("👈 サイドバーを確認してください。")
