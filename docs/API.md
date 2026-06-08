# API Reference

The backend is a FastAPI server. In development it runs on `http://localhost:8000`; in production the frontend can call it through `/api`.

## Authentication

### `POST /auth/register`

Creates a user and returns an auth token.

```json
{
  "username": "demo-user",
  "password": "password123"
}
```

### `POST /auth/login`

Logs in an existing user and returns an auth token.

### `GET /auth/me`

Returns the current user. Requires `Authorization: Bearer <token>`.

## Chat

### `POST /chat`

Streams an OpenAI-compatible chat completion through server-sent events.

Requires `Authorization: Bearer <token>`.

```json
{
  "provider": "deepseek",
  "message": "Summarize this project",
  "api_key": "sk-...",
  "base_url": "https://api.deepseek.com",
  "model_name": "deepseek-chat",
  "session_id": "default"
}
```

The stream emits JSON payloads in SSE `data:` lines:

```json
{ "type": "chunk", "content": "..." }
```

Errors are emitted as:

```json
{ "type": "error", "content": "..." }
```

## Agent Tasks

Agent tasks are semi-automatic. The backend first creates a plan and stores it as `waiting_confirmation`; the user must confirm before steps can run.

### `POST /agent/tasks`

Creates a task plan from a user goal.

### `GET /agent/tasks`

Lists the latest 50 tasks for the current user.

### `GET /agent/tasks/{task_id}`

Returns one task with its steps.

### `POST /agent/tasks/{task_id}/confirm`

Moves a planned task into `running`.

### `POST /agent/tasks/{task_id}/run`

Runs the next pending step. When all steps complete, the backend asks the model to produce a final Markdown result.

### `POST /agent/tasks/{task_id}/cancel`

Marks an unfinished task as failed.

## Safety Constraints

- Chat requests are rate-limited to 60 messages per user per hour.
- Base URLs must use HTTPS.
- Localhost, private IPs, link-local addresses, multicast, reserved, and unspecified addresses are blocked.
- Agent tools are limited to text-oriented planning, summarization, document generation, memory reading, and a placeholder search tool.

