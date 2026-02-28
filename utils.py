# utils.py
import streamlit as st
import google.generativeai as genai
import time
from datetime import datetime

CUSTOM_CSS = """<style>
    .stApp { background-color: #F0F8FF; color: #222222; }
    section[data-testid="stSidebar"] { background-color: #E6F3FF; }
    .stButton>button { width: 100%; border-radius: 5px; }
</style>"""

def add_to_history(action_type, content):
    if "history" not in st.session_state: st.session_state.history = []
    st.session_state.history.append({"time": datetime.now().strftime("%H:%M"), "type": action_type, "content": content})

def generate_content_with_retry(model_name, _content, prompt_text):
    api_key = st.session_state.get("user_input_key") or (st.secrets.get("ADMIN_API_KEY") if hasattr(st, "secrets") and "ADMIN_API_KEY" in st.secrets else None)
    if not api_key: return "Error: APIキーがありません"
    
    genai.configure(api_key=api_key, transport='rest')
    
    config = {
        "temperature": 0.4,          
        "max_output_tokens": 8192,   
        "top_p": 0.9
    }
    
    try:
        model = genai.GenerativeModel(model_name=model_name, generation_config=config)
    except Exception as e:
        return f"Error: AIモデルの準備に失敗しました。{str(e)}"

    last_error = ""
    max_retries = 4 
    
    for attempt in range(max_retries):
        try:
            payload = _content if _content else prompt_text
            response = model.generate_content(payload)
            
            if response.prompt_feedback and response.prompt_feedback.block_reason:
                return f"⚠️ Google APIの安全基準により生成がブロックされました。（理由: {response.prompt_feedback.block_reason}）"
            
            if response and hasattr(response, 'text'):
                return response.text
            else:
                raise ValueError("空のデータが返却されました")
                
        except Exception as e:
            last_error = str(e)
            wait_time = (2 ** attempt) + 2 
            
            if "429" in last_error or "exhausted" in last_error.lower() or "quota" in last_error.lower():
                time.sleep(wait_time)
                continue
            elif "500" in last_error or "Internal Server Error" in last_error or "503" in last_error:
                time.sleep(wait_time)
                continue
            elif "safety" in last_error.lower() or "block" in last_error.lower():
                return f"⚠️ コンテンツが安全基準に抵触したため生成できませんでした。（詳細: {last_error[:80]}）"
            else:
                time.sleep(wait_time)
                continue
            
    return f"⚠️ サーバーとの通信に失敗しました。資料が重すぎるか、サーバーが混雑しています。（詳細: {last_error[:80]}）"