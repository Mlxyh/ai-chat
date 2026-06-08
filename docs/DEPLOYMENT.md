# Deployment Guide

This project ships as a static Vue frontend plus a FastAPI backend.

## Local Development

Backend:

```bash
cd ai-backend
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
python main.py
```

Frontend:

```bash
cd ai-chat-ui
npm install
npm run dev
```

The development frontend reads `VITE_API_URL` from `ai-chat-ui/.env.development`.

## Production Build

Build the frontend:

```bash
cd ai-chat-ui
npm install
npm run build
```

The production build is generated in `ai-chat-ui/dist`.

Start the backend with a process manager such as systemd, pm2, supervisor, or a container runtime:

```bash
cd ai-backend
python -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/python main.py
```

On Linux, serve the backend behind a process manager rather than an interactive shell.

## Nginx

`deployment/mlxyh.nginx` is an example site configuration:

- Serves static files from `/var/www/mlxyh.com`.
- Proxies `/api/` to `http://127.0.0.1:8000/`.
- Uses `try_files` so Vue routes fall back to `index.html`.

Copy the built frontend files to the configured web root:

```bash
cp -r ai-chat-ui/dist/* /var/www/mlxyh.com/
```

Then install or reload the Nginx site according to your server layout.

## Data Files

The backend creates `ai-backend/app.db` automatically. Keep it on persistent storage and do not commit it.

Ignored runtime files include:

- `ai-backend/.env`
- `ai-backend/app.db`
- `ai-backend/.venv/`
- `ai-chat-ui/node_modules/`
- `ai-chat-ui/dist/`

