# Thumbtack 📌

**Multi-Agent Orchestrator Dashboard** — a self-hosted web UI for managing AI coding agents.

Built with FastAPI + WebSockets + SQLite. Dark themed.

## Features

- 🎨 **Dark Theme** — easy on the eyes
- 📁 **File Browser** — browse project files inline, send to agents with one click
- 🤖 **Agent Spawn/Kill** — Claude Code, Codex, OpenCode, Aider, or custom CLI
- 📊 **Agent Comparison Mode** — run Claude + Codex side-by-side on the same task
- 📝 **Task Queue** — queue up commands, agents work through them
- 💬 **WebSocket Streaming** — live stdout/stderr from all agents
- 💾 **SQLite Persistence** — session history survives restarts

## Quick Start

```bash
git clone https://github.com/JohnColling/Thumbtack.git
cd Thumbtack

python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# Note: uses `claude`, `codex`, `opencode`, `aider` CLI tools — install those first if you want those agents
python -m uvicorn main:app --host 0.0.0.0 --port 3456
```

Open `http://localhost:3456`

## License

MIT
