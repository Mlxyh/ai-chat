from collections import OrderedDict, defaultdict
from datetime import datetime, timedelta, timezone
import hashlib
import hmac
import ipaddress
import json
import secrets
import sqlite3
import socket
import time
from pathlib import Path
from typing import Optional, Tuple
from urllib.parse import urlparse

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
MAX_HISTORY_MESSAGES = 20
MAX_SESSIONS = 200
PROVIDER_DEFAULTS = {
    "deepseek": {
        "base_url": "https://api.deepseek.com",
        "model_name": "deepseek-chat",
    },
    "openai": {
        "base_url": "https://api.openai.com/v1",
        "model_name": "gpt-4o-mini",
    },
    "qwen": {
        "base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
        "model_name": "qwen-plus",
    },
}
BLOCKED_HOSTS = {"localhost", "localhost.localdomain"}
rate_store = defaultdict(lambda: {"count": 0, "reset_at": 0})
session_histories = OrderedDict()


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


class AgentModelConfig(BaseModel):
    provider: str
    api_key: str
    base_url: str
    model_name: str


class AgentTaskCreate(AgentModelConfig):
    goal: str


class AgentTaskAction(AgentModelConfig):
    pass


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
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS agent_tasks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                title TEXT NOT NULL,
                goal TEXT NOT NULL,
                status TEXT NOT NULL,
                plan TEXT NOT NULL DEFAULT '',
                final_result TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                FOREIGN KEY (user_id) REFERENCES users (id)
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS agent_steps (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                task_id INTEGER NOT NULL,
                step_order INTEGER NOT NULL,
                title TEXT NOT NULL,
                tool_name TEXT NOT NULL,
                status TEXT NOT NULL,
                input TEXT NOT NULL DEFAULT '',
                output TEXT NOT NULL DEFAULT '',
                error TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                FOREIGN KEY (task_id) REFERENCES agent_tasks (id)
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS agent_memories (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                memory_key TEXT NOT NULL,
                memory_value TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                UNIQUE(user_id, memory_key),
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
    now_iso = now.isoformat()
    with get_db() as conn:
        conn.execute("DELETE FROM auth_tokens WHERE expires_at <= ?", (now_iso,))
        conn.execute("DELETE FROM auth_tokens WHERE user_id = ?", (user_id,))
        conn.execute(
            "INSERT INTO auth_tokens (token, user_id, expires_at, created_at) VALUES (?, ?, ?, ?)",
            (token, user_id, expires_at.isoformat(), now_iso),
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


def get_session_history(session_key: str) -> list:
    history = session_histories.get(session_key)
    if history is None:
        history = []
        session_histories[session_key] = history
    else:
        session_histories.move_to_end(session_key)

    while len(session_histories) > MAX_SESSIONS:
        session_histories.popitem(last=False)
    return history


def trim_history(history: list):
    if len(history) > MAX_HISTORY_MESSAGES:
        del history[:-MAX_HISTORY_MESSAGES]


def is_blocked_ip(ip_text: str) -> bool:
    try:
        ip = ipaddress.ip_address(ip_text)
    except ValueError:
        return True
    return (
        ip.is_private
        or ip.is_loopback
        or ip.is_link_local
        or ip.is_multicast
        or ip.is_reserved
        or ip.is_unspecified
    )


def validate_base_url(base_url: str) -> str:
    value = base_url.strip().rstrip("/")
    parsed = urlparse(value)
    if parsed.scheme != "https" or not parsed.hostname:
        raise HTTPException(status_code=400, detail="Base URL 必须是有效的 HTTPS 地址")

    hostname = parsed.hostname.lower()
    if hostname in BLOCKED_HOSTS:
        raise HTTPException(status_code=400, detail="Base URL 不允许指向本机或内网地址")

    try:
        addresses = socket.getaddrinfo(hostname, None, proto=socket.IPPROTO_TCP)
    except socket.gaierror:
        raise HTTPException(status_code=400, detail="Base URL 域名无法解析")

    for address in addresses:
        if is_blocked_ip(address[4][0]):
            raise HTTPException(status_code=400, detail="Base URL 不允许指向本机或内网地址")

    return value


def resolve_model_config(data: ChatRequest) -> Tuple[str, str]:
    provider = data.provider.strip().lower()
    if provider in PROVIDER_DEFAULTS:
        defaults = PROVIDER_DEFAULTS[provider]
        base_url = data.base_url.strip() or defaults["base_url"]
        model_name = data.model_name.strip() or defaults["model_name"]
    elif provider == "custom":
        base_url = data.base_url.strip()
        model_name = data.model_name.strip()
    else:
        raise HTTPException(status_code=400, detail="不支持的模型服务")

    if not base_url or not model_name:
        raise HTTPException(status_code=400, detail="请填写 Base URL 和模型名称")

    return validate_base_url(base_url), model_name


def sse_payload(event_type: str, content: str) -> str:
    payload = json.dumps({"type": event_type, "content": content}, ensure_ascii=False)
    return f"data: {payload}\n\n"


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def model_config_from_action(data: AgentModelConfig) -> ChatRequest:
    return ChatRequest(
        provider=data.provider,
        message="",
        api_key=data.api_key,
        base_url=data.base_url,
        model_name=data.model_name,
    )


def call_model_once(data: AgentModelConfig, messages: list) -> str:
    if not data.api_key.strip():
        raise HTTPException(status_code=400, detail="请先填写当前模型的 API Key")
    chat_config = model_config_from_action(data)
    base_url, model_name = resolve_model_config(chat_config)
    headers = {
        "Authorization": f"Bearer {data.api_key.strip()}",
        "Content-Type": "application/json",
    }
    payload = {"model": model_name, "messages": messages, "stream": False}
    try:
        res = requests.post(
            build_chat_url(base_url),
            headers=headers,
            json=payload,
            timeout=90,
        )
        res.raise_for_status()
        body = res.json()
        return body.get("choices", [{}])[0].get("message", {}).get("content", "").strip()
    except requests.RequestException as e:
        print(f"agent model error: {type(e).__name__}: {e}")
        raise HTTPException(status_code=502, detail="模型服务连接失败，请检查 API Key、Base URL 或模型名称")
    except Exception as e:
        print(f"agent unexpected error: {type(e).__name__}: {e}")
        raise HTTPException(status_code=500, detail="智能体服务暂时不可用")


def fallback_plan(goal: str) -> dict:
    title = goal.strip()[:28] or "智能体任务"
    return {
        "title": title,
        "plan": "先理解目标，再拆解执行步骤，最后汇总交付结果。",
        "steps": [
            {"title": "理解目标与约束", "tool_name": "memory_reader", "input": goal},
            {"title": "生成执行方案", "tool_name": "document_generator", "input": goal},
            {"title": "汇总最终结果", "tool_name": "text_summarizer", "input": goal},
        ],
    }


def parse_plan(raw_text: str, goal: str) -> dict:
    try:
        start = raw_text.find("{")
        end = raw_text.rfind("}")
        payload = json.loads(raw_text[start : end + 1] if start >= 0 and end >= 0 else raw_text)
        steps = payload.get("steps") or []
        clean_steps = []
        for item in steps[:6]:
            title = str(item.get("title") or "").strip()
            if not title:
                continue
            tool_name = str(item.get("tool_name") or "document_generator").strip()
            if tool_name not in TOOL_REGISTRY:
                tool_name = "document_generator"
            clean_steps.append(
                {
                    "title": title[:80],
                    "tool_name": tool_name,
                    "input": str(item.get("input") or goal).strip(),
                }
            )
        if clean_steps:
            return {
                "title": str(payload.get("title") or goal[:28] or "智能体任务").strip()[:60],
                "plan": str(payload.get("plan") or raw_text).strip(),
                "steps": clean_steps,
            }
    except Exception:
        pass
    return fallback_plan(goal)


def create_agent_plan(data: AgentTaskCreate, user: dict) -> dict:
    prompt = f"""
你是一个半自动个人全能 AI 智能体。请为用户目标生成安全、可确认、只执行文本型任务的计划。
不要包含删除文件、提交代码、部署服务器、发送邮件、支付、下单等高风险动作。
只能使用这些工具名：web_search_placeholder, text_summarizer, document_generator, memory_reader。
请只返回 JSON，不要 Markdown。

用户：{user["username"]}
目标：{data.goal}

JSON 格式：
{{
  "title": "简短任务标题",
  "plan": "计划说明",
  "steps": [
    {{"title": "步骤标题", "tool_name": "document_generator", "input": "该步骤要处理的内容"}}
  ]
}}
"""
    raw = call_model_once(
        data,
        [
            {"role": "system", "content": "你是安全、谨慎、可审计的半自动 AI 智能体规划器。"},
            {"role": "user", "content": prompt},
        ],
    )
    return parse_plan(raw, data.goal)


def tool_web_search_placeholder(step: sqlite3.Row, task: sqlite3.Row, user: dict) -> str:
    return "联网搜索工具尚未开放。当前步骤已记录为待人工搜索，可先基于已有上下文继续分析。"


def tool_memory_reader(step: sqlite3.Row, task: sqlite3.Row, user: dict) -> str:
    with get_db() as conn:
        rows = conn.execute(
            "SELECT memory_key, memory_value FROM agent_memories WHERE user_id = ? ORDER BY updated_at DESC LIMIT 8",
            (user["id"],),
        ).fetchall()
    if not rows:
        return "暂无长期记忆。将使用当前任务目标和步骤上下文继续。"
    return "\n".join([f"- {row['memory_key']}: {row['memory_value']}" for row in rows])


def tool_text_summarizer(step: sqlite3.Row, task: sqlite3.Row, user: dict, data: AgentModelConfig) -> str:
    prior = get_step_context(task["id"])
    return call_model_once(
        data,
        [
            {"role": "system", "content": "你是严谨的总结助手，只基于给定内容输出清晰结论。"},
            {
                "role": "user",
                "content": f"任务目标：{task['goal']}\n当前步骤：{step['title']}\n步骤输入：{step['input']}\n已有上下文：\n{prior}\n\n请总结可执行结论。",
            },
        ],
    )


def tool_document_generator(step: sqlite3.Row, task: sqlite3.Row, user: dict, data: AgentModelConfig) -> str:
    prior = get_step_context(task["id"])
    return call_model_once(
        data,
        [
            {"role": "system", "content": "你是个人全能 AI 智能体，擅长把目标转成结构化交付物。"},
            {
                "role": "user",
                "content": f"任务目标：{task['goal']}\n当前步骤：{step['title']}\n步骤输入：{step['input']}\n已有步骤结果：\n{prior}\n\n请完成该步骤，输出 Markdown。",
            },
        ],
    )


TOOL_REGISTRY = {
    "web_search_placeholder": tool_web_search_placeholder,
    "text_summarizer": tool_text_summarizer,
    "document_generator": tool_document_generator,
    "memory_reader": tool_memory_reader,
}


def get_step_context(task_id: int) -> str:
    with get_db() as conn:
        rows = conn.execute(
            """
            SELECT title, output FROM agent_steps
            WHERE task_id = ? AND status = 'completed'
            ORDER BY step_order
            """,
            (task_id,),
        ).fetchall()
    if not rows:
        return "暂无已完成步骤。"
    return "\n\n".join([f"## {row['title']}\n{row['output']}" for row in rows])


def serialize_task(task: sqlite3.Row, steps: list) -> dict:
    return {
        "id": task["id"],
        "title": task["title"],
        "goal": task["goal"],
        "status": task["status"],
        "plan": task["plan"],
        "final_result": task["final_result"],
        "created_at": task["created_at"],
        "updated_at": task["updated_at"],
        "steps": [
            {
                "id": step["id"],
                "step_order": step["step_order"],
                "title": step["title"],
                "tool_name": step["tool_name"],
                "status": step["status"],
                "input": step["input"],
                "output": step["output"],
                "error": step["error"],
                "created_at": step["created_at"],
                "updated_at": step["updated_at"],
            }
            for step in steps
        ],
    }


def fetch_task_for_user(task_id: int, user_id: int) -> Tuple[sqlite3.Row, list]:
    with get_db() as conn:
        task = conn.execute(
            "SELECT * FROM agent_tasks WHERE id = ? AND user_id = ?",
            (task_id, user_id),
        ).fetchone()
        if not task:
            raise HTTPException(status_code=404, detail="任务不存在")
        steps = conn.execute(
            "SELECT * FROM agent_steps WHERE task_id = ? ORDER BY step_order",
            (task_id,),
        ).fetchall()
    return task, steps


def complete_task_if_done(task_id: int, data: AgentModelConfig, user: dict):
    task, steps = fetch_task_for_user(task_id, user["id"])
    if not steps or any(step["status"] != "completed" for step in steps):
        return
    context = get_step_context(task_id)
    final_result = call_model_once(
        data,
        [
            {"role": "system", "content": "你是个人全能 AI 智能体，请把所有步骤结果汇总成最终交付物。"},
            {"role": "user", "content": f"任务目标：{task['goal']}\n步骤结果：\n{context}\n\n请输出最终结果，使用 Markdown。"},
        ],
    )
    current = now_iso()
    with get_db() as conn:
        conn.execute(
            "UPDATE agent_tasks SET status = ?, final_result = ?, updated_at = ? WHERE id = ?",
            ("completed", final_result, current, task_id),
        )


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


@app.post("/agent/tasks")
def create_agent_task(data: AgentTaskCreate, user=Depends(get_current_user)):
    goal = data.goal.strip()
    if not goal:
        raise HTTPException(status_code=400, detail="任务目标不能为空")

    plan = create_agent_plan(data, user)
    current = now_iso()
    with get_db() as conn:
        cursor = conn.execute(
            """
            INSERT INTO agent_tasks (user_id, title, goal, status, plan, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                user["id"],
                plan["title"],
                goal,
                "waiting_confirmation",
                plan["plan"],
                current,
                current,
            ),
        )
        task_id = cursor.lastrowid
        for index, step in enumerate(plan["steps"], start=1):
            conn.execute(
                """
                INSERT INTO agent_steps
                (task_id, step_order, title, tool_name, status, input, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    task_id,
                    index,
                    step["title"],
                    step["tool_name"],
                    "pending",
                    step.get("input") or goal,
                    current,
                    current,
                ),
            )

    task, steps = fetch_task_for_user(task_id, user["id"])
    return {"task": serialize_task(task, steps)}


@app.get("/agent/tasks")
def list_agent_tasks(user=Depends(get_current_user)):
    with get_db() as conn:
        rows = conn.execute(
            """
            SELECT id, title, goal, status, plan, final_result, created_at, updated_at
            FROM agent_tasks
            WHERE user_id = ?
            ORDER BY updated_at DESC
            LIMIT 50
            """,
            (user["id"],),
        ).fetchall()
    return {
        "tasks": [
            {
                "id": row["id"],
                "title": row["title"],
                "goal": row["goal"],
                "status": row["status"],
                "plan": row["plan"],
                "final_result": row["final_result"],
                "created_at": row["created_at"],
                "updated_at": row["updated_at"],
            }
            for row in rows
        ]
    }


@app.get("/agent/tasks/{task_id}")
def get_agent_task(task_id: int, user=Depends(get_current_user)):
    task, steps = fetch_task_for_user(task_id, user["id"])
    return {"task": serialize_task(task, steps)}


@app.post("/agent/tasks/{task_id}/confirm")
def confirm_agent_task(task_id: int, user=Depends(get_current_user)):
    task, steps = fetch_task_for_user(task_id, user["id"])
    if task["status"] != "waiting_confirmation":
        raise HTTPException(status_code=400, detail="当前任务不需要确认")
    current = now_iso()
    with get_db() as conn:
        conn.execute(
            "UPDATE agent_tasks SET status = ?, updated_at = ? WHERE id = ?",
            ("running", current, task_id),
        )
    task, steps = fetch_task_for_user(task_id, user["id"])
    return {"task": serialize_task(task, steps)}


@app.post("/agent/tasks/{task_id}/cancel")
def cancel_agent_task(task_id: int, user=Depends(get_current_user)):
    task, steps = fetch_task_for_user(task_id, user["id"])
    if task["status"] in ("completed", "failed"):
        raise HTTPException(status_code=400, detail="任务已结束")
    current = now_iso()
    with get_db() as conn:
        conn.execute(
            "UPDATE agent_tasks SET status = ?, updated_at = ? WHERE id = ?",
            ("failed", current, task_id),
        )
    task, steps = fetch_task_for_user(task_id, user["id"])
    return {"task": serialize_task(task, steps)}


@app.post("/agent/tasks/{task_id}/run")
def run_agent_task(task_id: int, data: AgentTaskAction, user=Depends(get_current_user)):
    task, steps = fetch_task_for_user(task_id, user["id"])
    if task["status"] == "waiting_confirmation":
        raise HTTPException(status_code=400, detail="请先确认执行此计划")
    if task["status"] in ("completed", "failed"):
        return {"task": serialize_task(task, steps)}
    if task["status"] != "running":
        raise HTTPException(status_code=400, detail="任务状态不允许执行")

    next_step = next((step for step in steps if step["status"] == "pending"), None)
    if not next_step:
        complete_task_if_done(task_id, data, user)
        task, steps = fetch_task_for_user(task_id, user["id"])
        return {"task": serialize_task(task, steps)}

    current = now_iso()
    with get_db() as conn:
        conn.execute(
            "UPDATE agent_steps SET status = ?, updated_at = ? WHERE id = ?",
            ("running", current, next_step["id"]),
        )

    try:
        tool = TOOL_REGISTRY.get(next_step["tool_name"], tool_document_generator)
        if next_step["tool_name"] in ("text_summarizer", "document_generator"):
            output = tool(next_step, task, user, data)
        else:
            output = tool(next_step, task, user)
        status = "completed"
        error = ""
    except HTTPException:
        raise
    except Exception as e:
        print(f"agent step error: {type(e).__name__}: {e}")
        output = ""
        status = "failed"
        error = "该步骤执行失败，请调整任务后重试"

    current = now_iso()
    with get_db() as conn:
        conn.execute(
            """
            UPDATE agent_steps
            SET status = ?, output = ?, error = ?, updated_at = ?
            WHERE id = ?
            """,
            (status, output, error, current, next_step["id"]),
        )
        conn.execute(
            "UPDATE agent_tasks SET status = ?, updated_at = ? WHERE id = ?",
            ("failed" if status == "failed" else "running", current, task_id),
        )

    if status == "completed":
        complete_task_if_done(task_id, data, user)
    task, steps = fetch_task_for_user(task_id, user["id"])
    return {"task": serialize_task(task, steps)}


@app.post("/chat")
def chat(data: ChatRequest, user=Depends(get_current_user)):
    if not check_rate_limit(user["id"]):
        return JSONResponse(status_code=429, content={"detail": "每小时限制60条消息，请稍后再试"})

    if not data.message.strip():
        raise HTTPException(status_code=400, detail="消息不能为空")
    if not data.api_key.strip():
        raise HTTPException(status_code=400, detail="请先填写当前模型的 API Key")
    base_url, model_name = resolve_model_config(data)

    session_key = f'{user["id"]}:{data.session_id}'
    history = get_session_history(session_key)

    def generate():
        for event_type, chunk in stream_openai_compatible(data, history, base_url, model_name):
            yield sse_payload(event_type, chunk)

    return StreamingResponse(generate(), media_type="text/event-stream")


def build_chat_url(base_url: str) -> str:
    value = base_url.strip().rstrip("/")
    if value.endswith("/chat/completions"):
        return value
    return f"{value}/chat/completions"


def stream_openai_compatible(data: ChatRequest, history: list, base_url: str, model_name: str):
    headers = {
        "Authorization": f"Bearer {data.api_key.strip()}",
        "Content-Type": "application/json",
    }
    prompt = data.message.strip()
    history.append({"role": "user", "content": prompt})
    payload = {
        "model": model_name,
        "messages": history[-10:],
        "stream": True,
    }
    full_reply = ""

    try:
        with requests.post(
            build_chat_url(base_url),
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
                        yield "chunk", content
                except Exception:
                    continue
    except requests.RequestException as e:
        print(f"chat proxy error: {type(e).__name__}: {e}")
        yield "error", "模型服务连接失败，请检查 API Key、Base URL 或模型名称"
    except Exception as e:
        print(f"chat unexpected error: {type(e).__name__}: {e}")
        yield "error", "服务暂时不可用，请稍后重试"

    history.append({"role": "assistant", "content": full_reply})
    trim_history(history)


init_db()

if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
