# app.py
import os, warnings, random, re, time, streamlit as st
import google.generativeai as genai
import fitz  # PyMuPDF
from PIL import Image
import pandas as pd 

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
        [t["mode_research"], t["mode_data"], t["mode_test"]],
        on_change=on_mode_change
    )

    st.markdown("---")
    st.markdown("### 🔑 認証システム")
    
    st.info("💡 **Proプラン (月額980円)**\n\n最上位AIモデル「Gemini Pro」による高度な論文解析・完全再現模試が使い放題になります。")
    purchase_url = "https://buy.stripe.com/test_xxxxxx"
    st.markdown(f"<a href='{purchase_url}' target='_blank'><button style='width:100%; border-radius:4px; background-color:#FF4B4B; color:white; border:none; padding:10px; font-weight:bold; cursor:pointer;'>💎 Proプランに登録する</button></a>", unsafe_allow_html=True)
    st.markdown("<p style='font-size: 11px; color: gray; text-align: center; margin-top: 5px;'>※パスワードの第三者への共有は利用規約違反となり、検知次第パスワードを無効化します。</p>", unsafe_allow_html=True)
    st.markdown("<br>", unsafe_allow_html=True)

    active_api_key = None
    
    user_pass = st.text_input("💎 Pro Pass (登録者専用)", type="password")
    
    valid_passes = [
        "admin",               
        "pro_2024_03_secure",  
        "test_pass_980"        
    ]
    
    if user_pass in valid_passes:
        st.success("🔓 Pro版として認証されました")
        if "ADMIN_API_KEY" in st.secrets: active_api_key = st.secrets["ADMIN_API_KEY"]
    else:
        user_api_key = st.text_input(t["api_label"], type="password", key="user_input_key")
        st.button("🔑 ご自身のAPIキーを適用 (完全無料)", use_container_width=True)
        st.markdown(f"<div style='text-align: right; font-size: 12px;'>👉 <a href='https://aistudio.google.com/app/apikey' target='_blank'>APIキー取得手順</a></div>", unsafe_allow_html=True)
        active_api_key = user_api_key

    selected_model_name = "gemini-3.0-flash" 
    if active_api_key:
        genai.configure(api_key=active_api_key, transport='rest')
        if not st.session_state.available_models:
            raw_models = [m.name for m in genai.list_models() if 'generateContent' in m.supported_generation_methods]
            advanced_models = [m for m in raw_models if not re.search(r'gemini-[12]\.', m)]
            if not advanced_models:
                advanced_models = ["models/gemini-3.1-pro", "models/gemini-3.0-pro", "models/gemini-3.0-flash"]
            st.session_state.available_models = advanced_models
            
        if st.session_state.available_models:
            selected_model_name = st.selectbox(t["model_label"], st.session_state.available_models)

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
    if app_mode != t["mode_data"]:
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
            rtab1, rtab2, rtab3, rtab4 = st.tabs(["⚔️ 比較・要約", "📊 画像解析", "📚 引用ガイド", "💬 Q&A"])
            with rtab1:
                # 【変更】「初学者」と「重要ポイント」をリストから除外し、2つのモードに絞り込む
                available_modes = [m for m in t["modes"] if "初学者" not in m and "重要ポイント" not in m]
                mode = st.radio(t["prompt_summary_mode"], available_modes, horizontal=True)
                
                if st.button("📝 解析を実行", key="btn_sum"):
                    with st.spinner("圧倒的な情報量と分かりやすさで解析中... (数十秒かかる場合があります)"):
                        txt = "\n".join(st.session_state.pdf_texts.values())[:15000]
                        
                        if "IMRAD" in mode or "IMRAD" in mode.upper():
                            specific_instruction = """
以下の資料【全体】を一つの研究論文として捉え、【IMRAD形式】で専門家レベルの構造化要約を作成してください。
単なる表面的な要約ではなく、全体を通した具体的な「数値」「実験条件」「論理展開」を必ず抽出し、**読者がこの要約だけで原著論文を完全に理解できるレベルの「圧倒的な情報量（ボリューム）」と「分かりやすさ」**を両立させてください。

【出力フォーマット】
## 📌 I (Introduction: 導入・背景)
- 研究の背景とこれまでの課題（なぜこの研究が必要だったのか、背景を詳しく解説）
- この資料全体の目的と検証したい仮説

## 🔬 M (Methods: 方法)
- 対象・サンプル・使用機器（具体的な条件、サンプル数などを明記）
- 実験・調査・分析の具体的な手順（ステップバイステップで詳細に）

## 📊 R (Results: 結果)
【重要: 最も詳細に記述するセクションです。圧倒的なボリュームで抽出してください】
- 得られたすべての主要なデータ・発見（箇条書きで具体的に列挙）
- 重要な「具体的な数値」「パーセンテージ」「倍率」「統計的有意差（p値など）」を必ず明記
- 比較結果（対照群との違い、条件AとBの差など）を明確に記述
- データの具体的な傾向や、もしあれば例外的な結果

## 🧠 D (Discussion: 考察・結論)
- 結果から導き出される論理的な結論とメカニズム（なぜその結果になったのか、論理のプロセスを分かりやすく解説）
- この研究全体の限界点（Limitation）や今後の課題・展望
"""
                        elif "一般" in mode or "General" in mode:
                            specific_instruction = """
以下の資料の「核心となる情報」を抽出し、極めて具体的かつ詳細に深掘りして要約してください。
抽象的な表現（例：「〜について述べられている」「〜が調査された」）は絶対に避け、実際に「何が分かり」「どういうデータが出たのか」を明記すること。
また、**読者がこの要約を読むだけで資料の全貌を完全に理解できるレベルの「圧倒的な情報量（ボリューム）」と「分かりやすさ」**を持たせてください。

【出力フォーマット】
## 🎯 資料の核心・結論（一言で言うと何か）
- (資料が最も主張したい結論を具体的に、かつ分かりやすく)

## 💡 主要な発見と詳細なデータ（重要度の高い順に、ボリュームを持たせて）
- (具体的な数値や事実に基づく発見を深掘りして、多数の箇条書きで列挙)
- (抽象的な言葉を避け、事実と結果を詳細に記載)

## ⚙️ 採用されたアプローチ・根拠
- (どのような手法・データに基づいてその結論に至ったか、論理のプロセスを詳しく解説)

## ⚠️ 留意点・限界・今後の展望
- (資料から読み取れる制約や、次に繋がる課題)
"""
                        else:
                            specific_instruction = f"以下の資料全体を「{mode}」の形式で極めて具体的かつ圧倒的なボリュームで要約・整理してください。"

                        prompt_sum = f"""{t['ai_instruction']}
{specific_instruction}

【絶対厳守ルール】
1. 「料理のレシピ」等の無関係な言葉や、AIの自己紹介、前置きの挨拶は一切出力しないこと。
2. 資料のテキストには「【ページ X】」という表記が含まれていますが、ページごとに分割して同じような要約を何度も繰り返す（ループする）ことは絶対に禁止します。必ず「資料全体で1つの統合された要約」を作成してください。
3. 指定されたフォーマットに則り、学術的かつプロフェッショナルな分析結果のみを直接出力すること。
4. 【重要】要約だからといって短く省略しないでください。重要なデータ、数値、論理展開はすべて残し、圧倒的なボリュームと分かりやすさを担保すること。

資料:
{txt}"""
                        res = generate_content_with_retry(selected_model_name, None, prompt_sum)
                        st.markdown(res); add_to_history(f"要約({mode})", res)
            
            with rtab2:
                if u_img:
                    if st.button("🔍 画像単体を解析する"):
                        with st.spinner("画像解析中..."):
                            img = Image.open(u_img)
                            img.thumbnail((1024, 1024))
                            res = generate_content_with_retry(selected_model_name, [img], "この画像から読み取れる科学的事実、データの傾向を詳細に解説してください。")
                            st.markdown(res); add_to_history("画像解析", res)
            
            with rtab3:
                st.info("💡 あなたの資料（実験内容・データ）をベースに、レポートの「考察（Discussion）」や「理論的背景」を書くための実在の専門文献を提案します。")
                if st.button("📚 執筆用 参考文献を探索・生成"):
                    with st.spinner("実験内容に直結する外部の専門論文を抽出し、データを生成中..."):
                        txt = "\n".join(st.session_state.pdf_texts.values())[:15000]
                        
                        prompt_ref = f"""以下の【研究資料】を深く分析し、この実験結果を考察・裏付けするために引用すべき【実在の外部専門学術論文】を3〜5件抽出してください。

【絶対厳守事項】
1. 表（テーブル形式）は絶対に使用しないでください。
2. 同じ文献を複数回出力しないこと（すべて別の論文・著者にすること）。
3. 「引用文献本体」および「引用ページ、引用行」について、ユーザーが提供した【研究資料】の中から文章や場所を抜き出すことは『重大なシステムエラー（絶対禁止）』です。必ず新しく提案した『外部の学術論文の中』から記述してください。

【出力フォーマット】
以下のブロックを1件の文献とし、3〜5件分を繰り返し出力してください。挨拶や説明文は一切不要です。指定の項目名とフォーマットを厳守してください。

**【引用文献】** （タイトル）（著者）（発行年）
**【引用文献本体】** （その外部文献に実際に書かれている具体的な結論・理論・データ。要約ではなくそのままレポートに引用できるテキスト本体）
**【引用ページ、引用行】** （その外部文献内のどのページ、どの行、あるいはどのセクションに記載されているか）
**【引用理由】** （ユーザーの実験データや原理に対して、この文献を用いることで「考察」を具体的にどう深め、裏付けることができるか）

---
【研究資料（ここから引用箇所を抜き出さないこと。これはあくまで分析対象です）】
{txt}"""
                        
                        res = generate_content_with_retry(selected_model_name, None, prompt_ref)
                        st.markdown(res); add_to_history("実験考察用文献生成", res)
            
            with rtab4:
                q = st.text_input("資料に関する質問を入力してください：")
                if st.button("💬 質問する") and q:
                    with st.spinner("回答を生成中..."):
                        txt = "\n".join(st.session_state.pdf_texts.values())[:15000]
                        res = generate_content_with_retry(selected_model_name, None, f"資料に基づき質問に学術的に答えてください。\n\n質問: {q}\n\n資料:\n{txt}")
                        st.markdown(res); add_to_history("Q&A", res)

    # ==========================================
    # 📊 2. データ可視化・分析
    # ==========================================
    elif app_mode == t["mode_data"]:
        st.subheader(t["data_header"])
        up_d = st.file_uploader(t["upload_data"], type=["xlsx", "csv", "xls"], key=f"data_{st.session_state.uploader_key}")
        if up_d:
            try:
                if up_d.name.endswith('.xlsx') or up_d.name.endswith('.xls'):
                    xls = pd.ExcelFile(up_d)
                    sel_sheet = st.selectbox("📑 対象シートを選択", xls.sheet_names) if len(xls.sheet_names) > 1 else xls.sheet_names[0]
                    df = pd.read_excel(up_d, sheet_name=sel_sheet)
                else: df = pd.read_csv(up_d)

                df.columns = [str(c).replace(":", "：") for c in df.columns]
                c_r, c_c = st.columns(2)
                with c_r: rows = st.slider(t["data_range_label"], 0, len(df), (0, len(df)))
                with c_c: cols = st.multiselect("使用する列を選択", df.columns.tolist(), default=df.columns.tolist())
                
                if cols:
                    df_sel = df.iloc[rows[0]:rows[1]][cols]
                    st.dataframe(df_sel)
                    st.markdown("---")
                    v_col1, v_col2, v_col3 = st.columns(3)
                    with v_col1: x_col = st.selectbox("X軸 (横軸)", cols)
                    with v_col2: y_col = st.multiselect("Y軸 (縦軸)", [c for c in cols if c != x_col])
                    with v_col3: chart_type = st.selectbox("グラフの種類", ["折れ線グラフ (Line)", "棒グラフ (Bar)", "散布図 (Scatter)"])
                    
                    if st.button("グラフを描画"):
                        if y_col:
                            chart_data = df_sel[[x_col] + y_col]
                            if "Line" in chart_type: st.line_chart(chart_data, x=x_col, y=y_col)
                            elif "Bar" in chart_type: st.bar_chart(chart_data, x=x_col, y=y_col)
                            elif "Scatter" in chart_type: st.scatter_chart(chart_data, x=x_col, y=y_col)
                    
                    st.markdown("---")
                    if st.button("AIでデータを分析"):
                        with st.spinner("分析中..."):
                            res = generate_content_with_retry(selected_model_name, None, f"以下のデータセットの傾向や相関関係をプロとして詳細に分析してください。\n\n{df_sel.describe().to_markdown()}")
                            st.markdown(res); add_to_history("データ分析", res)
            except Exception as e: st.error(f"データ読み込みエラー: {e}")

    # ==========================================
    # 🎓 3. テスト対策
    # ==========================================
    elif app_mode == t["mode_test"]:
        st.info("💡 テスト対策モード: 資料（PDF・画像）からの問題作成、AI添削、解答生成、模試生成を一元管理します。")
        tab1, tab2, tab3, tab4 = st.tabs([
            "✍️ オリジナル問題作成", 
            "🧠 AI添削・採点", 
            "📝 資料の解答・解説生成", 
            "🔄 完全再現模試 (β)"      
        ])
        
        material_payload = []
        if st.session_state.pdf_texts:
            combined_text = "\n".join(st.session_state.pdf_texts.values())[:20000]
            material_payload.append(combined_text)
        if st.session_state.pdf_images:
            for imgs in st.session_state.pdf_images.values():
                material_payload.extend(imgs)
        if u_img:
            img = Image.open(u_img)
            img.thumbnail((1024, 1024))
            material_payload.append(img)
            
        is_material_loaded = len(material_payload) > 0

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
                        payload_q = list(material_payload) 
                        
                        prompt_q = f"""対象レベル「{t_level}」のプロの試験作成者として、添付資料から完全に新しいオリジナルの問題を作成せよ。難易度: {diff}、形式: {t_type}。
【絶対厳守ルール】
1. 問題編のテキストのみを出力すること。プログラムコードブロックは使用禁止。
2. 「問題に誤りがある可能性」「必ずしも成立しない」等のAI特有のメタ発言や逃げ口上は絶対禁止。必ず論理的に解ける完全な問題を作成すること。
3. 指定された【対象レベル】の学習指導要領の範囲を厳守すること。arccos, arcsin等の逸脱した大学数学の範囲は絶対に使用しないこと。
4. 数式は必ずLaTeX形式（インラインは $数式$、ブロックは $$数式$$）を使用すること。`^` や `*` などのプレーンテキスト表記は禁止。"""
                        payload_q.append(prompt_q)
                        res_q = generate_content_with_retry(selected_model_name, payload_q, prompt_q)
                        res_q_clean = re.sub(r'```[a-zA-Z]*\n|\n```|```', '', res_q).strip()
                        
                    if "⚠️" not in res_q_clean and "Error" not in res_q_clean:
                        with st.spinner("問題に対する『解答・解説』を生成中..."):
                            payload_a = payload_q[:-1]
                            
                            prompt_a = f"""以下の問題に対する【すべての正解と、論理的で質の高い解説】を作成せよ。
【作成された問題】
{res_q_clean}

【絶対厳守ルール】
1. プログラムコードブロック使用禁止。
2. 「問題に誤りがある」「解けない可能性がある」といった逃げ口上は絶対禁止。必ず断定的なトーンで正解を導き出すこと。
3. 指定された【対象レベル】の教育課程の範囲内で解説すること（逸脱した知識・逆三角関数等の使用は禁止）。
4. 数式は必ずLaTeX形式（インラインは $数式$、ブロックは $$数式$$）を使用すること。`^`や`*`のプレーンテキスト表記は厳禁。"""
                            payload_a.append(prompt_a)
                            res_a = generate_content_with_retry(selected_model_name, payload_a, prompt_a)
                            res_a_clean = re.sub(r'```[a-zA-Z]*\n|\n```|```', '', res_a).strip()
                            
                        st.session_state.test_result_obj = {"q": res_q_clean, "a": res_a_clean}
                        add_to_history(f"テスト作成 ({diff})", f"### 📝 問題編\n{res_q_clean}\n\n---\n### ✅ 模範解答と詳細解説\n{res_a_clean}")
            
            if st.session_state.test_result_obj:
                st.markdown("### 📝 問題編")
                st.markdown(st.session_state.test_result_obj["q"])
                with st.expander("✅ 模範解答と詳細解説を開く"): st.markdown(st.session_state.test_result_obj["a"])

        with tab2:
            if st.session_state.test_result_obj:
                u_text = st.text_area("テキスト回答エリア：", height=150)
                u_img_ans = st.file_uploader("手書きノートを写真で提出：", type=["png", "jpg", "jpeg"], key="grading_img")
                if st.button("AI採点官に提出する", type="primary"):
                    with st.spinner("採点中..."):
                        p_load = []
                        if u_img_ans:
                            ans_img = Image.open(u_img_ans)
                            ans_img.thumbnail((1024, 1024))
                            p_load.append(ans_img)
                        p = f"問題と模範解答を基準に、生徒の解答を採点・添削せよ。\n【問題】:\n{st.session_state.test_result_obj['q']}\n【模範解答】:\n{st.session_state.test_result_obj['a']}\n【生徒の解答】:\n{u_text if u_text else '画像参照'}"
                        p_load.append(p)
                        st.session_state.solve_feedback = generate_content_with_retry(selected_model_name, p_load, p)
                        add_to_history("テスト採点", st.session_state.solve_feedback)
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
                            st.error(f"エラーが発生しました: {e}")

        with tab4:
            if not is_material_loaded:
                st.warning("👆 上のエリアから対象となる問題集（PDFまたは画像）をアップロードしてください。")
            else:
                st.warning("⚠️ 【ベータ機能】アップロードされた資料（PDF/画像）の構造を解析し、全く同じ形式・難易度の別問題（模試）を生成します。")
                t_level_mock = st.selectbox("模試を生成する対象レベル（学習指導要領）", t["test_levels"], key="mock_level")
                if st.button("🔄 完全再現模試を生成する", type="primary"):
                    engine = ExamEngine(selected_model_name, active_api_key, target_level=t_level_mock)
                    try:
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
                        st.error(f"模試の生成中にエラーが発生しました。\n{e}")

else:
    st.warning("👈 サイドバーで設定を完了してください。")