from collections import defaultdict
from datetime import datetime, timedelta, timezone
import hashlib
import hmac
import json
import secrets
import sqlite3
import time
from pathlib import Path
from typing import Optional

import requests
from fastapi import Depends, FastAPI, Header, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel


app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

DB_PATH = Path(__file__).with_name("app.db")
TOKEN_TTL_DAYS = 7
RATE_LIMIT = 60
rate_store = defaultdict(lambda: {"count": 0, "reset_at": 0})
session_histories = defaultdict(list)


class AuthRequest(BaseModel):
    username: str
    password: str


class ChatRequest(BaseModel):
    provider: str
    message: str
    api_key: str
    base_url: str
    model_name: str
    session_id: str = "default"


def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    with get_db() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT NOT NULL UNIQUE,
                password_hash TEXT NOT NULL,
                salt TEXT NOT NULL,
                created_at TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS auth_tokens (
                token TEXT PRIMARY KEY,
                user_id INTEGER NOT NULL,
                expires_at TEXT NOT NULL,
                created_at TEXT NOT NULL,
                FOREIGN KEY (user_id) REFERENCES users (id)
            )
            """
        )


def normalize_username(username: str) -> str:
    value = username.strip()
    if len(value) < 3 or len(value) > 32:
        raise HTTPException(status_code=400, detail="用户名长度需要在3到32个字符之间")
    if not all(ch.isalnum() or ch in ("_", "-") for ch in value):
        raise HTTPException(status_code=400, detail="用户名只能包含字母、数字、下划线或短横线")
    return value


def validate_password(password: str):
    if len(password) < 6:
        raise HTTPException(status_code=400, detail="密码至少需要6个字符")


def hash_password(password: str, salt: str) -> str:
    digest = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        salt.encode("utf-8"),
        120_000,
    )
    return digest.hex()


def create_token(user_id: int) -> str:
    token = secrets.token_urlsafe(32)
    now = datetime.now(timezone.utc)
    expires_at = now + timedelta(days=TOKEN_TTL_DAYS)
    with get_db() as conn:
        conn.execute(
            "INSERT INTO auth_tokens (token, user_id, expires_at, created_at) VALUES (?, ?, ?, ?)",
            (token, user_id, expires_at.isoformat(), now.isoformat()),
        )
    return token


def serialize_user(row: sqlite3.Row) -> dict:
    return {"id": row["id"], "username": row["username"]}


def get_current_user(authorization: Optional[str] = Header(default=None)):
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=401, detail="请先登录")

    token = authorization.split(" ", 1)[1].strip()
    now = datetime.now(timezone.utc)

    with get_db() as conn:
        row = conn.execute(
            """
            SELECT users.id, users.username, auth_tokens.expires_at
            FROM auth_tokens
            JOIN users ON users.id = auth_tokens.user_id
            WHERE auth_tokens.token = ?
            """,
            (token,),
        ).fetchone()

    if not row:
        raise HTTPException(status_code=401, detail="登录状态无效")

    expires_at = datetime.fromisoformat(row["expires_at"])
    if expires_at < now:
        with get_db() as conn:
            conn.execute("DELETE FROM auth_tokens WHERE token = ?", (token,))
        raise HTTPException(status_code=401, detail="登录已过期，请重新登录")

    return serialize_user(row)


def check_rate_limit(user_id: int) -> bool:
    now = time.time()
    record = rate_store[user_id]
    if now > record["reset_at"]:
        record["count"] = 0
        record["reset_at"] = now + 3600
    if record["count"] >= RATE_LIMIT:
        return False
    record["count"] += 1
    return True


@app.post("/auth/register")
def register(data: AuthRequest):
    username = normalize_username(data.username)
    validate_password(data.password)
    salt = secrets.token_hex(16)
    password_hash = hash_password(data.password, salt)
    now = datetime.now(timezone.utc).isoformat()

    try:
        with get_db() as conn:
            cursor = conn.execute(
                """
                INSERT INTO users (username, password_hash, salt, created_at)
                VALUES (?, ?, ?, ?)
                """,
                (username, password_hash, salt, now),
            )
            user_id = cursor.lastrowid
    except sqlite3.IntegrityError:
        raise HTTPException(status_code=409, detail="用户名已存在")

    token = create_token(user_id)
    return {"token": token, "user": {"id": user_id, "username": username}}


@app.post("/auth/login")
def login(data: AuthRequest):
    username = normalize_username(data.username)
    with get_db() as conn:
        user = conn.execute(
            "SELECT id, username, password_hash, salt FROM users WHERE username = ?",
            (username,),
        ).fetchone()

    if not user:
        raise HTTPException(status_code=401, detail="用户名或密码错误")

    expected_hash = hash_password(data.password, user["salt"])
    if not hmac.compare_digest(expected_hash, user["password_hash"]):
        raise HTTPException(status_code=401, detail="用户名或密码错误")

    token = create_token(user["id"])
    return {"token": token, "user": serialize_user(user)}


@app.get("/auth/me")
def me(user=Depends(get_current_user)):
    return {"user": user}


@app.post("/chat")
def chat(data: ChatRequest, user=Depends(get_current_user)):
    if not check_rate_limit(user["id"]):
        return JSONResponse(status_code=429, content={"detail": "每小时限制60条消息，请稍后再试"})

    if not data.message.strip():
        raise HTTPException(status_code=400, detail="消息不能为空")
    if not data.api_key.strip():
        raise HTTPException(status_code=400, detail="请先填写当前模型的 API Key")
    if not data.base_url.strip() or not data.model_name.strip():
        raise HTTPException(status_code=400, detail="请填写 Base URL 和模型名称")

    session_key = f'{user["id"]}:{data.session_id}'
    history = session_histories[session_key]

    def generate():
        for chunk in stream_openai_compatible(data, history):
            yield f"data: {chunk}\n\n"

    return StreamingResponse(generate(), media_type="text/event-stream")


def build_chat_url(base_url: str) -> str:
    value = base_url.strip().rstrip("/")
    if value.endswith("/chat/completions"):
        return value
    return f"{value}/chat/completions"


def stream_openai_compatible(data: ChatRequest, history: list):
    headers = {
        "Authorization": f"Bearer {data.api_key.strip()}",
        "Content-Type": "application/json",
    }
    prompt = data.message.strip()
    history.append({"role": "user", "content": prompt})
    payload = {
        "model": data.model_name.strip(),
        "messages": history[-10:],
        "stream": True,
    }
    full_reply = ""

    try:
        with requests.post(
            build_chat_url(data.base_url),
            headers=headers,
            json=payload,
            stream=True,
            timeout=60,
        ) as res:
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


init_db()

if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
