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

# ★ ここで分割した2つのファイルを読み込みます ★
from mode_research import render_research_mode
from mode_test import render_test_mode

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
            st.error("🚨 【エラー】APIキーの中に全角文字が混ざっています。修正してください。")
            st.stop()

        try:
            genai.configure(api_key=active_api_key, transport='rest')
            if not st.session_state.available_models:
                raw_models = [m.name for m in genai.list_models() if 'generateContent' in m.supported_generation_methods]
                advanced_models = [m for m in raw_models if 'gemini-3' in m and 'gemma' not in m.lower()]
                if not advanced_models:
                    advanced_models = ["models/gemini-3.1-pro", "models/gemini-3.0-pro", "models/gemini-3.0-flash"]
                st.session_state.available_models = advanced_models
                
            if st.session_state.available_models:
                selected_model_name = st.selectbox(t["model_label"], st.session_state.available_models)
        except Exception as e:
            st.error(f"🚨 API連携エラーが発生しました。詳細: {e}")

    st.markdown("---")
    st.markdown("### 🌐 翻訳サポート")
    st.info("専門用語などを確認したい場合はこちら👇")
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
                    for i in range(min(20, len(pdf_doc))):
                        page = pdf_doc.load_page(i)
                        pix = page.get_pixmap(matrix=fitz.Matrix(2, 2))
                        img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
                        img.thumbnail((1024, 1024))
                        images.append(img)
                    st.session_state.pdf_images[f.name] = images

    with c2:
        u_img = st.file_uploader(t["upload_img"], type=["png", "jpg", "jpeg"], key=f"img_{st.session_state.uploader_key}_{app_mode}")

    # ==========================================
    # ★ モード切り替え（分割したファイルを呼び出す） ★
    # ==========================================
    if app_mode == t["mode_research"]:
        # 論文解析モードの変数を準備
        res_images = []
        if u_img:
            img_obj = Image.open(u_img)
            img_obj.thumbnail((1024, 1024))
            res_images.append(img_obj)
        if st.session_state.pdf_images:
            for imgs in st.session_state.pdf_images.values():
                res_images.extend(imgs)
        txt = "\n".join(st.session_state.pdf_texts.values())[:100000]
        
        # 関数を実行
        render_research_mode(selected_model_name, res_images, txt, t, u_img)

    elif app_mode == t["mode_test"]:
        # テスト対策モードの変数を準備
        combined_text = ""
        if st.session_state.pdf_texts:
            combined_text = "\n".join(st.session_state.pdf_texts.values())[:100000]
            
        image_payload = []
        if st.session_state.pdf_images:
            for imgs in st.session_state.pdf_images.values():
                image_payload.extend(imgs)
        if u_img:
            img = Image.open(u_img)
            img.thumbnail((1024, 1024))
            image_payload.append(img)
            
        is_material_loaded = bool(combined_text) or len(image_payload) > 0

        # 関数を実行
        render_test_mode(selected_model_name, active_api_key, image_payload, combined_text, is_material_loaded, t, u_img)

else:
    st.warning("👈 サイドバーで設定を完了してください。")
