# AI Chat

AI Chat is a private model gateway and agent workspace. It provides a Vue 3 web UI, a FastAPI backend, user authentication, streamed chat, and a confirm-before-run agent task flow for OpenAI-compatible model providers.

## Features

- Account login and registration backed by SQLite.
- Bring-your-own API key for DeepSeek, OpenAI, Qwen, or any OpenAI-compatible HTTPS endpoint.
- Streaming chat through a backend proxy with Markdown rendering and code copy buttons.
- Agent task planning with manual confirmation before execution.
- Per-user task history, step timeline, cancellation, and final Markdown delivery.
- Backend safeguards for rate limits, HTTPS-only Base URLs, and local/private network blocking.
- Production-ready Nginx example for serving the frontend and proxying `/api`.

## Project Structure

```text
.
├── ai-backend/       # FastAPI API server and SQLite data store
├── ai-chat-ui/       # Vue 3 + Vite frontend
├── deployment/       # Nginx deployment example
└── docs/             # API and deployment documentation
```

## Quick Start

Start the backend:

```bash
cd ai-backend
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
python main.py
```

Start the frontend:

```bash
cd ai-chat-ui
npm install
npm run dev
```

Then open the Vite URL and register an account. The frontend uses `VITE_API_URL=http://localhost:8000` in development.

## Configuration

The app is designed for bring-your-own model credentials. API keys are entered in the browser UI and sent to the backend only for the active request; they are not stored by the backend.

Supported provider defaults:

| Provider | Default Base URL | Default Model |
| --- | --- | --- |
| DeepSeek | `https://api.deepseek.com` | `deepseek-chat` |
| OpenAI | `https://api.openai.com/v1` | `gpt-4o-mini` |
| Qwen | `https://dashscope.aliyuncs.com/compatible-mode/v1` | `qwen-plus` |
| Custom | User-provided HTTPS URL | User-provided model |

## Documentation

- [API reference](docs/API.md)
- [Deployment guide](docs/DEPLOYMENT.md)
- [Frontend notes](ai-chat-ui/README.md)

## Security Notes

- Do not commit `ai-backend/.env`, `ai-backend/app.db`, virtual environments, or build output.
- The backend rejects non-HTTPS Base URLs and hostnames that resolve to local or private networks.
- User passwords are salted and hashed with PBKDF2-HMAC-SHA256.
- Auth tokens expire after 7 days.

