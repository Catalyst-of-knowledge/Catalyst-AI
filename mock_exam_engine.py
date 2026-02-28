# mock_exam_engine.py
import time
import json
import re
import google.generativeai as genai
from pydantic import BaseModel, Field

class QuestionBlueprint(BaseModel):
    q_num: int = Field(description="問題番号")
    q_type: str = Field(description="形式(選択, 記述, 穴埋めなど)")
    theme: str = Field(description="問われている知識やテーマ")
    difficulty: int = Field(description="難易度(1〜5)")

class ExamBlueprint(BaseModel):
    total_q: int = Field(description="総問題数")
    questions: list[QuestionBlueprint] = Field(description="各問題の設計図")

class MockQuestion(BaseModel):
    question_text: str = Field(description="生成された問題文")
    answer: str = Field(description="正答")
    explanation: str = Field(description="詳細な解説")

class ExamEngine:
    def __init__(self, model_name, api_key, target_level="高校生"):
        genai.configure(api_key=api_key, transport='rest')
        self.model_name = model_name
        self.target_level = target_level

    def _extract_json(self, text: str) -> dict:
        text = text.strip()
        # Markdownのコードブロック記法が混ざった場合のクリーニング
        text = re.sub(r'^```[a-zA-Z]*\n', '', text)
        text = re.sub(r'\n```$', '', text)
        
        match = re.search(r'\{[\s\S]*\}', text)
        if match:
            json_str = match.group(0)
            try:
                json_str = re.sub(r'\[\s*\d+\s*:\s*\{', '[ {', json_str)
                return json.loads(json_str)
            except json.JSONDecodeError as e:
                raise ValueError(f"AIが不正なJSONを出力しました。パース失敗: {e}\n抽出されたテキスト: {json_str[:200]}")
        raise ValueError(f"AIの出力から有効なJSON構造を発見できませんでした。\n出力内容: {text[:200]}")

    def solve_material(self, payload: list) -> str:
        model = genai.GenerativeModel(self.model_name)
        prompt = f"""以下の資料（画像およびテキスト）は試験問題または課題です。プロの講師として、すべての問題に対する「明確な解答」と「論理的で分かりやすい解説」を作成してください。

        【絶対厳守ルール（違反は重大なシステムエラー）】
        1. 対象レベル: {self.target_level}。この教育課程・学習指導要領の範囲を厳守すること（例: 高校レベルなら大学数学の知識や公式は使用禁止）。
        2. メタ発言の禁止: 「問題文に誤りがある可能性がある」「必ずしも成立しない」といった推測や言い訳、逃げ口上は一切記述せず、与えられた情報から断定的に解答を導き出すこと。
        3. 数式フォーマット: 数式はすべて必ずLaTeX形式（インラインは $数式$、ブロックは $$数式$$）で出力すること。`^` (累乗) や `*` (掛け算) を用いたプレーンテキストの数式表現は絶対に使用しないこと。"""
        
        response = model.generate_content([prompt] + payload)
        return response.text if response else "エラー: 解答を生成できませんでした。"

    def analyze_material_structure(self, payload: list) -> ExamBlueprint:
        model = genai.GenerativeModel(self.model_name)
        prompt = """以下の試験問題（資料）を深く読み込み、大問・小問の数、各形式、問われている具体的なテーマ、難易度(1〜5)を厳密に解析しなさい。

        【絶対厳守フォーマット】
        必ず以下のRFC 8259準拠の完全なJSON形式のみを出力すること。配列の中に `0:` のようなインデックスを書いてはならない。
        また、下のJSONはあくまで「構造の例」である。「テーマ名」などのダミーテキストをそのままコピー出力した場合はシステムが停止する。必ず「資料から読み取った実際のデータ」を代入すること。

        {
            "total_q": (実際の総問題数を整数で記載),
            "questions": [
                {
                    "q_num": 1,
                    "q_type": "(例: 選択式、穴埋め、記述など実際の形式)",
                    "theme": "(例: 微分積分、日本の歴史など、資料から読み取った具体的なテーマ)",
                    "difficulty": (1から5の整数)
                }
            ]
        }
        """
        try:
            response = model.generate_content([prompt] + payload)
            json_data = self._extract_json(response.text)
            return ExamBlueprint.model_validate(json_data)
        except Exception as e:
            raise ValueError(f"構造解析エラー: AIが資料の読み取りを放棄したか、不正なフォーマットを出力しました。\n詳細: {e}")

    def generate_mock_question(self, blueprint: QuestionBlueprint, context_payload: list) -> MockQuestion:
        model = genai.GenerativeModel(self.model_name)
        prompt = f"""あなたはプロの試験作成者です。以下の【条件】に完全に一致する、オリジナルで新しい問題と解答・解説を作成しなさい。

        【条件】
        - 形式: {blueprint.q_type}
        - テーマ: {blueprint.theme}
        - 難易度(1-5): {blueprint.difficulty}
        - 対象レベル: {self.target_level}
        
        【絶対厳守ルール（違反は重大なシステムエラー）】
        1. 教育課程の厳守: 指定された【対象レベル】の学習指導要領を絶対に逸脱しないこと。例えば高校レベルの問題にarccosやarcsin等の大学数学を含めることは厳禁である。
        2. 逃げ口上の禁止: 「〜の可能性がある」「問題に不備があるかもしれない」「成立しない場合がある」などのメタ発言・言い訳を一切禁止する。論理的に完全に解ける完成された問題を、断定的なトーンで記述すること。
        3. 数式フォーマット: 数式はすべて必ずLaTeX形式（インラインは $数式$、ブロックは $$数式$$）で出力すること。`^` や `*` を用いたプレーンテキストの数式表現は絶対に使用しないこと。

        【絶対厳守フォーマット】
        出力は以下のJSONのみとすること。挨拶、コードブロック、マークダウン装飾、補足説明は一切不要。
        {{
            "question_text": "ここに具体的な問題文を記述（数式はLaTeX化）",
            "answer": "ここに正答を記述",
            "explanation": "ここに解説を断定的なトーンで記述（数式はLaTeX化）"
        }}"""
        
        last_error = ""
        # 【429エラー完全対応】最大4回までリトライし、制限に引っかかったら60秒待機する
        for attempt in range(4):
            try:
                response = model.generate_content([prompt] + context_payload)
                json_data = self._extract_json(response.text)
                return MockQuestion.model_validate(json_data)
            except Exception as e:
                last_error = str(e)
                error_msg = last_error.lower()
                # 429エラー（Quota Exceeded）を検知した場合、60秒間強制スリープしてAPI枠を回復させる
                if "429" in error_msg or "quota" in error_msg:
                    time.sleep(60)
                else:
                    time.sleep(5)
        raise RuntimeError(f"問{blueprint.q_num}の生成に失敗しました。詳細: {last_error}")