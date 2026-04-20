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
            st.error("🚨 【エラー】APIキーの中に「日本語」「全角スペース」または「全角クォーテーション」が混ざっています。修正してください。")
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
            st.error(f"🚨 API連携エラーが発生しました。APIキーが間違っている可能性があります。詳細: {e}")

    st.markdown("---")
    st.markdown("### 🌐 翻訳サポート")
    st.info("英語の専門用語や元の論文を確認したい場合はこちら👇")
    st.markdown("👉 **[DeepL翻訳を開く](https://www.deepl.com/translator)**")

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
        current_files = [f.name for f in ufs] if ufs else []
        
        for name in list(st.session_state.pdf_texts.keys()):
            if name not in current_files:
                del st.session_state.pdf_texts[name]
                if name in st.session_state.pdf_images: del st.session_state.pdf_images[name]
                    
        if ufs:
            for f in ufs:
                if f.name not in st.session_state.pdf_texts:
                    file_bytes = f.read()
                    pdf_doc = fitz.open(stream=file_bytes, filetype="pdf")
                    
                    extracted_text = []
                    for p_idx, page in enumerate(pdf_doc): 
                        extracted_text.append(f"【ページ {p_idx + 1}】\n{page.get_text()}")
                    st.session_state.pdf_texts[f.name] = "\n".join(extracted_text)
                    
                    images = []
                    for i in range(min(3, len(pdf_doc))):
                        page = pdf_doc.load_page(i)
                        pix = page.get_pixmap(matrix=fitz.Matrix(2, 2))
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
        st.subheader(t["mode_research"])
        if not st.session_state.pdf_texts and not u_img:
            st.warning("👆 上のエリアから資料をアップロードしてください。")
        else:
            res_images = []
            if u_img:
                img_obj = Image.open(u_img)
                img_obj.thumbnail((1024, 1024))
                res_images.append(img_obj)
            if st.session_state.pdf_images:
                for imgs in st.session_state.pdf_images.values():
                    res_images.extend(imgs)
            txt = "\n".join(st.session_state.pdf_texts.values())[:15000]

            rtab1, rtab2, rtab3, rtab4 = st.tabs(["⚔️ 構造化要約", "📊 画像解析", "📚 引用ガイド", "💬 Q&A"])
            with rtab1:
                st.info("💡 資料を「要旨」「目的」「実験操作」「結果」「考察」などの9項目に分けて、圧倒的なボリュームで詳細に構造化要約します。")
                
                if st.button("📝 構造化要約を実行", key="btn_sum", type="primary"):
                    with st.spinner("資料を解析し、日本語に翻訳・構造化しています..."):
                        specific_instruction = """
あなたはプロの翻訳家および研究者です。以下の資料の情報を抽出し、ユーザーが指定した以下の段取り（構成）に沿って極めて具体的かつ詳細に深掘りして要約してください。
読者がこの要約を読むだけで資料の全貌を完全に理解できるレベルの「圧倒的な情報量（ボリューム）」を持たせてください。

【出力フォーマット（必ず以下の見出しを順番通りに使用すること）】

## 📑 要旨
- (資料全体の簡単な概要)

## 📝 本文の要約
- (本文全体の詳細な要約)

## 🎯 目的
- (この資料・研究が何を目的に行われたか)

## 🔬 実験操作、方法
- (どのような手法・データ・実験操作に基づいて行われたか詳細に)

## 📊 結果
- (具体的な数値や事実に基づく発見を深掘りして列挙。圧倒的なボリュームで抽出すること)

## 🤔 考察
- (結果から導き出される論理的な考察やメカニズム)

## ✅ 結論
- (最終的な結論)

## 🚀 未来への展望、疑問
- (資料から読み取れる今後の展望や残された課題・疑問点)

## 🔑 Keyワード、重要ポイント、用語
- (重要なキーワードや専門用語の解説、最重要ポイントの箇条書き)
"""
                        # 【改善ポイント】AIが英語に引きずられないよう、資料の「後」に日本語化の強制コマンドを配置
                        prompt_sum = f"""{t['ai_instruction']}
{specific_instruction}

【絶対厳守ルール】
1. 前置きの挨拶、AIの自己紹介などは一切出力しないこと。
2. ページごとに分割して同じ要約を繰り返す（ループ処理）ことは禁止。資料全体で1つの統合された要約を作成すること。
3. 要約だからといって短く省略せず、重要なデータ、数値、論理展開はすべて残すこと。

【対象の資料テキスト】
{txt if txt else '（テキストデータなし。添付の画像データを参照してください）'}

---
【🚨 最終強制コマンド（最重要）】
上記の資料が英語等の外国語であっても、出力は【必ずすべて日本語（Japanese）】に翻訳して記述してください。
見出し、本文、説明のすべてにおいて、英語のまま出力することは重大なシステムエラーとみなします。必ず日本語で答えてください。
"""
                        try:
                            res = generate_content_with_retry(selected_model_name, res_images if res_images else None, prompt_sum)
                            st.markdown(res); add_to_history("構造化要約", res)
                        except Exception as e:
                            if "429" in str(e):
                                st.error("⏳ **サーバー通信制限（429エラー）**\n\n短時間に大量のデータ（PDFや画像）を送信したため、一時的に通信制限がかかりました。**1〜2分ほど待ってから**、再度ボタンを押してください。")
                            else:
                                st.error(f"AIの生成中にエラーが発生しました: {e}")
            
            with rtab2:
                if u_img:
                    if st.button("🔍 画像単体を解析する"):
                        with st.spinner("画像解析中..."):
                            try:
                                img = Image.open(u_img)
                                img.thumbnail((1024, 1024))
                                res = generate_content_with_retry(selected_model_name, [img], "この画像から読み取れる科学的事実、データの傾向を詳細に解説してください。\n\n【🚨 絶対厳守】出力は必ずすべて日本語（Japanese）で行うこと。英語は使用禁止です。")
                                st.markdown(res); add_to_history("画像解析", res)
                            except Exception as e:
                                if "429" in str(e):
                                    st.error("⏳ 通信制限中です。1〜2分待ってから再度お試しください。")
                                else:
                                    st.error(f"画像解析中にエラーが発生しました: {e}")
            
            with rtab3:
                st.info("💡 あなたの資料（実験結果・データ）をベースに、レポートの「考察（Discussion）」を執筆・裏付けするために引用すべき、実在の専門学術論文を提案します。")
                if st.button("📚 執筆用 参考文献を探索・生成"):
                    with st.spinner("AIの幻覚（ハルシネーション）を排除し、実在する信頼性の高い学術論文を厳選中..."):
                        prompt_ref = f"""以下の【研究資料】（ユーザーの実験結果や画像データ等）を深く分析し、この結果を「考察（Discussion）」で裏付け、より深い議論を展開するために引用すべき【実在する極めて信頼性の高い学術論文・専門書】を3件厳選して提案してください。

【🚨 幻覚（ハルシネーション）絶対禁止ルール】
AI特有の「存在しない架空の論文」をでっち上げることは重大なシステムエラーです。
1. 誰もが検索して見つけられる、歴史的・基礎的、あるいはその分野で非常に有名な「確実に実在する文献」のみを提案すること。
2. 架空のページ数や行数を捏造しないこと。
3. ユーザーの資料内の文章を「外部文献の引用」としてそのままコピペ出力しないこと。

【出力フォーマット】（以下の項目も日本語で出力すること）
以下のブロックを1件の文献とし、3件分を繰り返し出力してください。挨拶や説明文は一切不要です。指定の項目名とフォーマットを厳守してください。

### 📚 提案文献
- **タイトル:** (必ず実在するタイトル)
- **著者・発行年:** (必ず実在する著者と年)
- **🔍検索キーワード:** (ユーザーがGoogle Scholar等でこの論文を確実に見つけるためのキーワードやDOI)

### 🔬 引用すべき「核心の理論・データ」
- (この外部文献において、証明されている事実や提唱されている理論を解説。AIの推測ではなく、その論文が実際に主張している内容を書くこと)

### 💡 あなたの資料との「繋がり（考察への組み込み方）」
- (ユーザーの資料の【どのデータや結果】に対して、この文献の理論を【どう結びつければ】、レポートの「考察」として説得力が増すのか。そのままレポートに使えるレベルの論理展開の筋道を提案すること)

---
【研究資料テキスト（画像が添付されている場合は画像も参照）】
{txt if txt else '（テキストデータなし。添付の画像データを参照してください）'}

---
【🚨 最終強制コマンド（最重要）】
出力結果（解説や提案理由など）は【必ずすべて日本語 (Japanese)】に翻訳して記述してください。英語のまま出力することは重大なエラーです。
"""
                        try:
                            res = generate_content_with_retry(selected_model_name, res_images if res_images else None, prompt_ref)
                            st.markdown(res); add_to_history("実験考察用文献生成", res)
                        except Exception as e:
                            if "429" in str(e):
                                st.error("⏳ 通信制限中です。1〜2分待ってから再度お試しください。")
                            else:
                                st.error(f"参考文献生成中にエラーが発生しました: {e}")
            
            with rtab4:
                q = st.text_input("資料に関する質問を入力してください：")
                if st.button("💬 質問する") and q:
                    with st.spinner("回答を生成中..."):
                        try:
                            res = generate_content_with_retry(selected_model_name, res_images if res_images else None, f"資料（画像およびテキスト）に基づき質問に学術的に答えてください。\n\n質問: {q}\n\n資料:\n{txt}\n\n---\n【最重要】回答は必ずすべて日本語(Japanese)に翻訳して行うこと。")
                            st.markdown(res); add_to_history("Q&A", res)
                        except Exception as e:
                            if "429" in str(e):
                                st.error("⏳ 通信制限中です。1〜2分待ってから再度お試しください。")
                            else:
                                st.error(f"回答生成中にエラーが発生しました: {e}")

    # ==========================================
    # 🎓 2. テスト対策
    # ==========================================
    elif app_mode == t["mode_test"]:
        st.info("💡 テスト対策モード: 資料（PDF・画像）からの問題作成、AI添削、解答生成、模試生成を一元管理します。")
        tab1, tab2, tab3, tab4 = st.tabs([
            "✍️ オリジナル問題作成", 
            "🧠 AI添削・採点", 
            "📝 資料の解答・解説生成", 
            "🔄 完全再現模試 (β)"      
        ])
        
        combined_text = ""
        if st.session_state.pdf_texts:
            combined_text = "\n".join(st.session_state.pdf_texts.values())[:20000]
            
        image_payload = []
        if st.session_state.pdf_images:
            for imgs in st.session_state.pdf_images.values():
                image_payload.extend(imgs)
        if u_img:
            img = Image.open(u_img)
            img.thumbnail((1024, 1024))
            image_payload.append(img)
            
        is_material_loaded = bool(combined_text) or len(image_payload) > 0

        material_payload = []
        if combined_text: material_payload.append(combined_text)
        material_payload.extend(image_payload)

        with tab1:
            ca, cb = st.columns(2)
            with ca: 
                t_level = st.selectbox(t["test_level_label"], t["test_levels"])
                t_type = st.selectbox(t["test_type_label"], t["test_types"])
            with cb: diff = st.selectbox(t["test_diff_label"], t["test_diffs"])
            
            if st.button(t["test_btn"], type="primary"):
                if not is_material_loaded:
                    st.error("❌ 上部のエリアから画像資料またはPDFをアップロードしてください。")
                else:
                    with st.spinner("資料から高品質な問題を生成中..."):
                        prompt_q = f"""対象レベル「{t_level}」のプロの試験作成者として、添付資料から完全に新しいオリジナルの問題を作成せよ。難易度: {diff}、形式: {t_type}。

【参考資料テキスト（画像が添付されている場合は画像も参照）】
{combined_text if combined_text else '（テキストなし。添付の画像データを参照）'}

【絶対厳守ルール】
1. 問題編のテキストのみを出力すること。プログラムコードブロックは使用禁止。
2. 「問題に誤りがある可能性」「必ずしも成立しない」等のAI特有のメタ発言や逃げ口上は絶対禁止。必ず論理的に解ける完全な問題を作成すること。
3. 指定された【対象レベル】の学習指導要領の範囲を厳守すること。arccos, arcsin等の逸脱した大学数学の範囲は絶対に使用しないこと。
4. 数式は必ずLaTeX形式（インラインは $数式$、ブロックは $$数式$$）を使用すること。`^` や `*` などのプレーンテキスト表記は禁止。

---
【重要：言語指定】
作成する問題文は必ずすべて日本語(Japanese)で翻訳・記述すること。"""
                        try:
                            res_q = generate_content_with_retry(selected_model_name, image_payload if image_payload else None, prompt_q)
                            res_q_clean = re.sub(r'```[a-zA-Z]*\n|\n```|```', '', res_q).strip()
                            
                            if "⚠️" not in res_q_clean and "Error" not in res_q_clean:
                                with st.spinner("問題に対する『解答・解説』を生成中..."):
                                    prompt_a = f"""以下の問題に対する【すべての正解と、論理的で質の高い解説】を作成せよ。

【作成された問題】
{res_q_clean}

【参考資料テキスト（画像が添付されている場合は画像も参照）】
{combined_text if combined_text else '（テキストなし。添付の画像データを参照）'}

【絶対厳守ルール】
1. プログラムコードブロック使用禁止。
2. 「問題に誤りがある」「解けない可能性がある」といった逃げ口上は絶対禁止。必ず断定的なトーンで正解を導き出すこと。
3. 指定された【対象レベル】の教育課程の範囲内で解説すること（逸脱した知識・逆三角関数等の使用は禁止）。
4. 数式は必ずLaTeX形式（インラインは $数式$、ブロックは $$数式$$）を使用すること。`^`や`*`のプレーンテキスト表記は厳禁。

---
【重要：言語指定】
解答および解説は必ずすべて日本語(Japanese)で記述すること。"""
                                    
                                    res_a = generate_content_with_retry(selected_model_name, image_payload if image_payload else None, prompt_a)
                                    res_a_clean = re.sub(r'```[a-zA-Z]*\n|\n```|```', '', res_a).strip()
                                    
                                st.session_state.test_result_obj = {"q": res_q_clean, "a": res_a_clean}
                                add_to_history(f"テスト作成 ({diff})", f"### 📝 問題編\n{res_q_clean}\n\n---\n### ✅ 模範解答と詳細解説\n{res_a_clean}")
                        except Exception as e:
                            if "429" in str(e):
                                st.error("⏳ 通信制限中です。1〜2分待ってから再度お試しください。")
                            else:
                                st.error(f"問題作成中にエラーが発生しました: {e}")
            
            if st.session_state.test_result_obj:
                st.markdown("### 📝 問題編")
                st.markdown(st.session_state.test_result_obj["q"])
                with st.expander("✅ 模範解答と詳細解説を開く"): st.markdown(st.session_state.test_result_obj["a"])

        with tab2:
            if st.session_state.test_result_obj:
                u_text = st.text_area("テキスト回答エリア：", height=150)
                u_img_ans = st.file_uploader("手書きノートを写真で提出：", type=["png", "jpg", "jpeg"], key="grading_img")
                if st.button("AI採点官に提出する", type="primary"):
                    if not u_text.strip() and not u_img_ans:
                        st.warning("⚠️ 採点を行うためには、テキスト入力欄に解答を入力するか、ノートの画像をアップロードしてください。")
                    else:
                        with st.spinner("採点中..."):
                            try:
                                p_load = []
                                if u_img_ans:
                                    ans_img = Image.open(u_img_ans)
                                    ans_img.thumbnail((1024, 1024))
                                    p_load.append(ans_img)
                                p = f"問題と模範解答を基準に、生徒の解答を採点・添削せよ。\n【問題】:\n{st.session_state.test_result_obj['q']}\n【模範解答】:\n{st.session_state.test_result_obj['a']}\n【生徒の解答】:\n{u_text if u_text else '画像参照'}\n\n---\n【重要】必ずすべて日本語(Japanese)で出力すること。"
                                st.session_state.solve_feedback = generate_content_with_retry(selected_model_name, p_load if p_load else None, p)
                                add_to_history("テスト採点", st.session_state.solve_feedback)
                            except Exception as e:
                                if "429" in str(e):
                                    st.error("⏳ 通信制限中です。1〜2分待ってから再度お試しください。")
                                else:
                                    st.error(f"採点中にエラーが発生しました: {e}")
                if st.session_state.solve_feedback: 
                    st.success("📊 添削・採点結果")
                    st.markdown(st.session_state.solve_feedback)
            else: st.warning("👈 まずは「オリジナル問題作成」タブでテストを作成してください。")

        with tab3:
            if not is_material_loaded:
                st.warning("👆 上のエリアから対象となる問題集（PDFまたは画像）をアップロードしてください。")
            else:
                st.info("アップロードされた問題（PDF/画像）の「解答・解説」を即座に生成します。")
                t_level_solve = st.selectbox("解答を作成する対象レベル（学習指導要領）", t["test_levels"], key="solve_level")
                if st.button("🧠 資料の解答・解説を生成する"):
                    with st.spinner("プロの視点で解答と解説を構築中..."):
                        try:
                            engine = ExamEngine(selected_model_name, active_api_key, target_level=t_level_solve)
                            res_solution = engine.solve_material(material_payload)
                            st.markdown("### ✅ 解答・解説")
                            st.markdown(res_solution)
                            add_to_history("資料解答・解説", res_solution)
                        except Exception as e:
                            if "429" in str(e):
                                st.error("⏳ 通信制限中です。1〜2分待ってから再度お試しください。")
                            else:
                                st.error(f"エラーが発生しました: {e}")

        with tab4:
            if not is_material_loaded:
                st.warning("👆 上のエリアから対象となる問題集（PDFまたは画像）をアップロードしてください。")
            else:
                st.warning("⚠️ 【ベータ機能】アップロードされた資料（PDF/画像）の構造を解析し、全く同じ形式・難易度の別問題（模試）を生成します。")
                t_level_mock = st.selectbox("模試を生成する対象レベル（学習指導要領）", t["test_levels"], key="mock_level")
                if st.button("🔄 完全再現模試を生成する", type="primary"):
                    try:
                        engine = ExamEngine(selected_model_name, active_api_key, target_level=t_level_mock)
                        with st.spinner("ステップ1: 資料の分量・難易度・形式を解析中..."):
                            blueprint = engine.analyze_material_structure(material_payload)
                            st.success(f"解析完了: 全{blueprint.total_q}問の構成を抽出しました。")
                            with st.expander("📊 抽出された設計図（内部データ）"): st.json(blueprint.model_dump())

                        st.markdown("### 📝 生成された完全再現模試")
                        progress_bar = st.progress(0)
                        
                        for idx, q_meta in enumerate(blueprint.questions):
                            if idx > 0:
                                time.sleep(3)

                            with st.spinner(f"ステップ2: 問{q_meta.q_num} を生成中... (※API制限を回避するため、長めに待機する場合があります)"):
                                mock_q = engine.generate_mock_question(q_meta, material_payload)
                                st.markdown(f"**問{q_meta.q_num}. ({q_meta.q_type})**\n{mock_q.question_text}")
                                with st.expander("解答と解説を見る"):
                                    st.markdown(f"**【正答】** {mock_q.answer}")
                                    st.markdown(f"**【解説】** {mock_q.explanation}")
                                st.markdown("---")
                                progress_bar.progress((idx + 1) / len(blueprint.questions))
                        
                        st.success("🎉 全ての模試生成が完了しました！")
                    except Exception as e:
                        if "429" in str(e):
                            st.error("⏳ 通信制限中です。1〜2分待ってから再度お試しください。")
                        else:
                            st.error(f"模試の生成中にエラーが発生しました。\n{e}")

else:
    st.warning("👈 サイドバーで設定を完了してください。")
