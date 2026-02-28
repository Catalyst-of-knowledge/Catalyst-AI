# languages.py

translations = {
    "Japanese": {
        "title": "🔬 Catalyst AI",
        "caption": "研究を加速する「知の超特急」 | 研究解析 & テスト対策",
        "api_label": "Gemini APIキー",
        "model_label": "🤖 使用モデルを選択",
        "header_upload": "1. Import (資料)",
        "upload_pdf": "📄 教科書・論文PDF",
        "upload_img": "🖼️ グラフ・図表・問題集 (画像)", 
        "header_analysis": "2. Analysis (分析)",
        "sidebar_mode_label": "🚀 動作モード選択",
        "mode_research": "🔬 論文・資料解析",
        "mode_data": "📊 データ可視化・分析",
        "mode_test": "🎓 テスト対策", # 【修正】画像特化型の表記を削除
        "test_header": "🎓 予想問題作成",
        "test_type_label": "問題の形式",
        "test_types": ["📝 記述・論述式", "✅ 4択マークシート式", "🧮 計算・応用問題", "⭕ ◯×クイズ"],
        "test_level_label": "対象レベル (学習指導要領)",
        "test_levels": ["🎒 小学生", "🏫 中学生", "🎓 高校生", "🏛️ 大学生・一般"],
        "test_diff_label": "難易度 (資料との相対比較)",
        "test_diffs": ["🐣 基礎確認", "🐈 標準レベル", "🦁 難しい"],
        "test_btn": "予想問題を生成する",
        "test_submit_btn": "回答を提出して採点する",
        "test_feedback_header": "📊 採点結果・フィードバック",
        "test_sim_btn": "🔍 類似の過去問を検索",
        "data_header": "📊 データ可視化・分析エージェント", 
        "upload_data": "📈 Excel / CSVファイル", 
        "data_range_label": "✂️ 使用するデータ範囲 (行)", 
        "data_btn_ai": "AIでデータを分析",
        "history_title": "🕒 実行履歴",
        "history_empty": "履歴なし",
        "history_load": "📂 Load",
        "history_del": "🗑️ Delete",
        "new_create_btn": "➕ 新規作成",
        "close_view": "× 閉じる",
        "sidebar_note": "APIキー取得",
        "prompt_summary_mode": "要約モード:",
        "modes": ["🔰 初学者解説", "📑 一般的な要約", "🧬 IMRAD構造化要約", "💡 重要ポイントまとめ"],
        "prompt_summary_btn": "解析を実行",
        "prompt_ref_btn": "引用箇所をスキャン",
        "ai_instruction": "あなたは優秀な科学教育アシスタントです。日本語で出力してください。"
    }
}

affiliate_links = {
    "Japanese": [
        {"url": "https://www.amazon.co.jp/s?k=Python+データ分析", "text": "おすすめ：Pythonデータ分析", "price": "￥2,500〜", "image_url": "https://m.media-amazon.com/images/I/51rPqG-uV2L._AC_UY218_.jpg"},
        {"url": "https://www.amazon.co.jp/s?k=大学受験+化学+参考書", "text": "おすすめ：大学受験 化学", "price": "￥1,500〜", "image_url": "https://m.media-amazon.com/images/I/81x+mQ6JqIL._AC_UY218_.jpg"},
        {"url": "https://www.amazon.co.jp/s?k=TOEIC+公式問題集", "text": "おすすめ：TOEIC公式問題集", "price": "￥3,300〜", "image_url": "https://m.media-amazon.com/images/I/81V2vYQ6yML._AC_UY218_.jpg"},
        {"url": "https://www.amazon.co.jp/s?k=統計学入門", "text": "おすすめ：統計学入門", "price": "￥3,000〜", "image_url": "https://m.media-amazon.com/images/I/61L2iI4Rj6L._AC_UY218_.jpg"},
        {"url": "https://www.amazon.co.jp/s?k=iPad+Pro", "text": "学習環境を強化：iPad", "price": "詳細をチェック", "image_url": "https://m.media-amazon.com/images/I/61R-S894U9L._AC_UY218_.jpg"}
    ]
}