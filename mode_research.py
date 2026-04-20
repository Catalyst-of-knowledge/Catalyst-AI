import streamlit as st
from PIL import Image
from utils import generate_content_with_retry, add_to_history

def render_research_mode(selected_model_name, res_images, txt, t, u_img):
    st.subheader(t["mode_research"])
    if not txt and not res_images:
        st.warning("👆 上のエリアから資料をアップロードしてください。")
        return

    rtab1, rtab2, rtab3, rtab4 = st.tabs(["⚔️ 構造化要約", "📊 画像解析", "📚 引用ガイド", "💬 Q&A"])
    
    with rtab1:
        st.info("💡 資料を「要旨」「目的」「実験操作」「結果」「考察」などの9項目に分けて、圧倒的なボリュームで詳細に構造化要約します。")
        if st.button("📝 構造化要約を実行", key="btn_sum", type="primary"):
            with st.spinner("情報を最大限に引き出し、分量2倍で執筆しています... (長文になるため少し時間がかかります)"):
                prompt_sum = f"""
【絶対厳守の命令】
あなたは日本の専門研究員です。以下の資料を精読し、指定された9つの見出しに沿って、「通常の要約の2倍以上の圧倒的な文字数と情報量」で、極めて長文かつ詳細なレポートを作成してください。
出力は最初から最後まで、必ず「日本語（Japanese）」のみを使用してください。

【指定フォーマット（順番と見出しをそのまま使うこと）】
## 📑 要旨
## 📝 本文の要約
## 🎯 目的
## 🔬 実験操作、方法
## 📊 結果
## 🤔 考察
## ✅ 結論
## 🚀 未来への展望、疑問
## 🔑 Keyワード、重要ポイント、用語

【記述のルール：ボリュームの最大化】
1. 挨拶やAIとしての前置きは一切不要です。
2. 【分量2倍の強制】要約だからといって決して短くまとめないでください。各見出しについて、資料内の些細なデータ、数値、背景、論理展開のニュアンスに至るまで一切省略せず、可能な限り文章を徹底的に膨らませて、非常に長大な解説に仕上げてください。
3. すべて日本語で出力すること。

【資料内容】
{txt if txt else '（添付の画像データを参照してください）'}
"""
                try:
                    res = generate_content_with_retry(selected_model_name, res_images if res_images else None, prompt_sum)
                    st.markdown(res)
                    add_to_history("構造化要約", res)
                except Exception as e:
                    if "429" in str(e):
                        st.error("⏳ **サーバー通信制限（429エラー）**\n\n1〜2分ほど待ってから、再度ボタンを押してください。")
                    else:
                        st.error(f"AIの生成中にエラーが発生しました: {e}")
    
    with rtab2:
        if u_img:
            if st.button("🔍 画像単体を解析する"):
                with st.spinner("画像解析中..."):
                    try:
                        img = Image.open(u_img)
                        img.thumbnail((1024, 1024))
                        res = generate_content_with_retry(selected_model_name, [img], "【絶対厳守】必ずすべて「日本語（Japanese）」で記述してください。\nこの画像から読み取れる科学的事実、データの傾向を限界まで深掘りし、非常に詳細な長文で解説してください。")
                        st.markdown(res)
                        add_to_history("画像解析", res)
                    except Exception as e:
                        if "429" in str(e):
                            st.error("⏳ 通信制限中です。1〜2分待ってから再度お試しください。")
                        else:
                            st.error(f"画像解析中にエラーが発生しました: {e}")
    
    with rtab3:
        st.info("💡 あなたの資料（実験結果・データ）をベースに、レポートの「考察（Discussion）」を執筆・裏付けするために引用すべき、実在の専門学術論文を提案します。")
        if st.button("📚 執筆用 参考文献を探索・生成"):
            with st.spinner("AIの幻覚（ハルシネーション）を排除し、実在する信頼性の高い学術論文を厳選中..."):
                prompt_ref = f"""
【絶対厳守の命令】必ずすべて「日本語（Japanese）」で出力してください。

以下の【研究資料】を分析し、この結果を考察で裏付け、より深い議論を展開するために引用すべき【実在する信頼性の高い学術論文】を3件厳選して提案してください。

【厳守事項】
1. 確実に実在する文献のみを提案すること（幻覚の禁止）。
2. 架空のページ数などを捏造しないこと。

【出力フォーマット】
### 📚 提案文献
- **タイトル:** (実在するタイトル)
- **著者・発行年:** (実在する著者と年)
- **🔍検索キーワード:** (キーワードやDOI)

### 🔬 引用すべき「核心の理論・データ」
- (論文が主張している内容を日本語で詳細に解説)

### 💡 あなたの資料との「繋がり（考察への組み込み方）」
- (ユーザーの資料に対して、どう結びつければ説得力が増すかを日本語で詳細に提案)

---
【研究資料】
{txt if txt else '（添付の画像データを参照してください）'}
"""
                try:
                    res = generate_content_with_retry(selected_model_name, res_images if res_images else None, prompt_ref)
                    st.markdown(res)
                    add_to_history("実験考察用文献生成", res)
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
                    res = generate_content_with_retry(selected_model_name, res_images if res_images else None, f"【絶対厳守】必ずすべて「日本語（Japanese）」で記述してください。\n\n資料に基づき質問に学術的かつ非常に詳細な長文で答えてください。\n\n質問: {q}\n\n資料:\n{txt}")
                    st.markdown(res)
                    add_to_history("Q&A", res)
                except Exception as e:
                    if "429" in str(e):
                        st.error("⏳ 通信制限中です。1〜2分待ってから再度お試しください。")
                    else:
                        st.error(f"回答生成中にエラーが発生しました: {e}")
