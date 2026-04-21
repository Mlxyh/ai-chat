from fastapi import FastAPI
from fastapi.responses import StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import requests
import os
import json
from dotenv import load_dotenv

load_dotenv()

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
OPENAI_BASE_URL = os.getenv("OPENAI_BASE_URL", "https://api.openai.com")
QWEN_API_KEY = os.getenv("QWEN_API_KEY")

session_histories = {}

class ChatRequest(BaseModel):
    model: str
    message: str
    session_id: str = "default"

@app.post("/chat")
def chat(data: ChatRequest):
    history = session_histories.setdefault(data.session_id, [])

    if data.model == "openai":
        stream_fn = lambda: stream_openai(data.message, history)
    elif data.model == "qwen":
        stream_fn = lambda: stream_qwen(data.message, history)
    else:
        stream_fn = lambda: stream_deepseek(data.message, history)

    def generate():
        for chunk in stream_fn():
            yield f"data: {chunk}\n\n"

    return StreamingResponse(generate(), media_type="text/event-stream")

def _stream_openai_compatible(prompt, history, url, api_key, model_name):
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }
    history.append({"role": "user", "content": prompt})
    data = {"model": model_name, "messages": history[-10:], "stream": True}
    full_reply = ""

    try:
        with requests.post(url, headers=headers, json=data, stream=True, timeout=60) as res:
            res.raise_for_status()
            for line in res.iter_lines():
                if not line:
                    continue
                line = line.decode("utf-8")
                if not line.startswith("data: "):
                    continue
                line = line[6:]
                if line == "[DONE]":
                    break
                try:
                    chunk = json.loads(line)
                    content = chunk.get("choices", [{}])[0].get("delta", {}).get("content")
                    if content:
                        full_reply += content
                        yield content
                except Exception:
                    continue
    except Exception as e:
        yield f"\n\n[错误: {e}]"

    history.append({"role": "assistant", "content": full_reply})

def stream_deepseek(prompt, history):
    yield from _stream_openai_compatible(
        prompt, history,
        url="https://api.deepseek.com/chat/completions",
        api_key=DEEPSEEK_API_KEY,
        model_name="deepseek-chat"
    )

def stream_openai(prompt, history):
    yield from _stream_openai_compatible(
        prompt, history,
        url=f"{OPENAI_BASE_URL}/v1/chat/completions",
        api_key=OPENAI_API_KEY,
        model_name="gpt-4o-mini"
    )

def stream_qwen(prompt, history):
    yield from _stream_openai_compatible(
        prompt, history,
        url="https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions",
        api_key=QWEN_API_KEY,
        model_name="qwen-plus"
    )

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
