import streamlit as st
import re
import time
from PIL import Image
from utils import generate_content_with_retry, add_to_history
from mock_exam_engine import ExamEngine

def render_test_mode(selected_model_name, active_api_key, image_payload, combined_text, is_material_loaded, t, u_img):
    st.info("💡 テスト対策モード: 資料（PDF・画像）からの問題作成、AI添削、解答生成、模試生成を一元管理します。")
    tab1, tab2, tab3, tab4 = st.tabs([
        "✍️ オリジナル問題作成", 
        "🧠 AI添削・採点", 
        "📝 資料の解答・解説生成", 
        "🔄 完全再現模試 (β)"      
    ])

    with tab1:
        ca, cb = st.columns(2)
        with ca: 
            t_level = st.selectbox(t["test_level_label"], t["test_levels"])
            t_type = st.selectbox(t["test_type_label"], t["test_types"])
        with cb: 
            diff = st.selectbox(t["test_diff_label"], t["test_diffs"])
        
        if st.button(t["test_btn"], type="primary"):
            if not is_material_loaded:
                st.error("❌ 上部のエリアから画像資料またはPDFをアップロードしてください。")
            else:
                with st.spinner("全ページから高品質な問題を生成中..."):
                    prompt_q = f"""
【絶対厳守】必ずすべて「日本語（Japanese）」で記述してください。

対象レベル「{t_level}」のプロの試験作成者として、添付資料から完全に新しいオリジナルの問題を作成せよ。難易度: {diff}、形式: {t_type}。

【参考資料】
{combined_text if combined_text else '（画像データを参照）'}

【厳守ルール】
1. プログラムコードブロックは使用禁止。
2. 逃げ口上は絶対禁止。論理的に解ける完全な問題を作成すること。
3. 指定レベルの範囲を厳守すること。
4. 数式はLaTeX形式（インライン $数式$、ブロック $$数式$$）を使用すること。
"""
                    try:
                        res_q = generate_content_with_retry(selected_model_name, image_payload if image_payload else None, prompt_q)
                        res_q_clean = re.sub(r'```[a-zA-Z]*\n|\n```|```', '', res_q).strip()
                        
                        if "⚠️" not in res_q_clean and "Error" not in res_q_clean:
                            with st.spinner("問題に対する『解答・解説』を生成中..."):
                                prompt_a = f"""
【絶対厳守】必ずすべて「日本語（Japanese）」で記述してください。

以下の問題に対する【すべての正解と、論理的で極めて詳細な解説】を作成せよ。

【問題】
{res_q_clean}

【参考資料】
{combined_text if combined_text else '（画像データを参照）'}

【厳守ルール】
1. プログラムコードブロックは使用禁止。
2. 断定的なトーンで正解を導き出すこと。
3. 数式はLaTeX形式を使用すること。
"""
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
            with st.expander("✅ 模範解答と詳細解説を開く"): 
                st.markdown(st.session_state.test_result_obj["a"])

    with tab2:
        if st.session_state.test_result_obj:
            u_text = st.text_area("テキスト回答エリア：", height=150)
            u_img_ans = st.file_uploader("手書きノートを写真で提出：", type=["png", "jpg", "jpeg"], key="grading_img")
            if st.button("AI採点官に提出する", type="primary"):
                if not u_text.strip() and not u_img_ans:
                    st.warning("⚠️ 解答を入力するか、画像をアップロードしてください。")
                else:
                    with st.spinner("採点中..."):
                        try:
                            p_load = []
                            if u_img_ans:
                                ans_img = Image.open(u_img_ans)
                                ans_img.thumbnail((1024, 1024))
                                p_load.append(ans_img)
                            p = f"【絶対厳守】必ずすべて「日本語（Japanese）」で記述してください。\n\n問題と模範解答を基準に、生徒の解答を採点・添削せよ。\n【問題】:\n{st.session_state.test_result_obj['q']}\n【模範解答】:\n{st.session_state.test_result_obj['a']}\n【生徒の解答】:\n{u_text if u_text else '画像参照'}"
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
        else: 
            st.warning("👈 まずは「オリジナル問題作成」タブでテストを作成してください。")

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
                        res_solution = engine.solve_material(image_payload if image_payload else [combined_text])
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
                        blueprint = engine.analyze_material_structure(image_payload if image_payload else [combined_text])
                        st.success(f"解析完了: 全{blueprint.total_q}問の構成を抽出しました。")
                        with st.expander("📊 抽出された設計図（内部データ）"): 
                            st.json(blueprint.model_dump())

                    st.markdown("### 📝 生成された完全再現模試")
                    progress_bar = st.progress(0)
                    
                    for idx, q_meta in enumerate(blueprint.questions):
                        if idx > 0:
                            time.sleep(3)

                        with st.spinner(f"ステップ2: 問{q_meta.q_num} を生成中... (※API制限を回避するため、長めに待機する場合があります)"):
                            mock_q = engine.generate_mock_question(q_meta, image_payload if image_payload else [combined_text])
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
