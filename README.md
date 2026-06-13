# Robomix

Robomix is a minimal extraction from the original project:

- backend: FastAPI chat API with basic LLM streaming, ReAct tool calling, and EntroFlow device support
- frontend: one classic AI chat panel

## Backend

```bash
cd backend
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
uvicorn main:app --host 0.0.0.0 --port 3011 --reload
```

Set at least one model provider key in `.env`, or run Ollama locally.

EntroFlow is treated as an installed user dependency. Install it with the normal EntroFlow command first; Robomix then reads runtime code, assets, config, and registered devices from `~/.entroflow`.

## Frontend

```bash
cd frontend
npm install
VITE_API_BASE=http://localhost:3011 npm run dev -- --port 3010
```

The frontend calls `VITE_API_BASE` or defaults to `http://localhost:3011`.
