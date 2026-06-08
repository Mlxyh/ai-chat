# AI Chat UI

Vue 3 frontend for AI Chat, a private model gateway and agent workspace.

## What It Provides

- Login and registration screens.
- Provider settings for DeepSeek, OpenAI, Qwen, and custom OpenAI-compatible APIs.
- Streaming chat UI with Markdown and syntax highlighting.
- Agent task view with planning, confirmation, step execution, cancellation, and final results.
- Local browser storage for per-user provider settings and chat history.

## Development

```bash
npm install
npm run dev
```

Set the backend URL in `.env.development`:

```env
VITE_API_URL=http://localhost:8000
```

## Production

```bash
npm run build
```

The generated static assets are written to `dist/`.
