# Robomix

AI chat panel with LLM streaming, ReAct tool calling, and EntroFlow device control.  
Built for controlling physical robots and IoT devices from a single chat interface.

## Architecture

```
┌──────────────┐     HTTP/SSE      ┌──────────────┐     CLI/MCP     ┌────────────┐
│   frontend   │ ◄──────────────► │   backend    │ ◄─────────────► │ EntroFlow  │
│  React/Vite  │                   │  FastAPI     │                 │  Runtime   │
│  port 3010   │                   │  port 3011   │                 └────────────┘
└──────────────┘                   └──────────────┘
```

- **frontend**: React 19 + Vite + TypeScript, classic AI chat UI
- **backend**: FastAPI with SSE streaming, ReAct tool-calling loop, multi-provider LLM support
- **EntroFlow**: device discovery, status, and control through registered devices

## Dependencies

### Required

| Dependency | Version | Install |
|-----------|---------|---------|
| [EntroFlow](https://entroflow.ai) | latest | `curl -fsSL https://entroflow.ai/install \| bash` |
| Python | ≥ 3.10 | system / pyenv |
| Node.js | ≥ 18 | system / nvm |

### Optional (robot SDK)

| Dependency | Purpose |
|-----------|---------|
| Docker + Colima | ROS2 Humble container runtime |
| ROS2 Humble | AGIBOT robot control |
| OpenCV / Ruckig / cv_bridge | Robot SDK examples |

See [Dockerfile.ros2](Dockerfile.ros2) and [Dockerfile.sdk-deps](Dockerfile.sdk-deps).

## Quick Start

### 1. Install EntroFlow

```bash
# Follow the official install guide, then:
entroflow update
```

### 2. Install private EntroFlow resources

This repo includes a private UnixAI robot platform resource. Run the setup script:

```bash
bash scripts/setup-entroflow.sh
```

This copies `entroflow-assets/unixai/` to `~/.entroflow/assets/unixai/` and registers the device.

> **What's in `entroflow-assets/`?**
> - `unixai/connector/` — HTTP connector for the UnixAI robot control panel
> - `unixai/devices/unixai.robot/` — device driver with `speak`, `start_task`, `reset_task` actions
>
> These are **local-only resources** (not published to the EntroFlow platform).
> They live alongside EntroFlow's managed assets at `~/.entroflow/assets/unixai/`.

### 3. Start the backend

```bash
cd backend
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
# Edit .env with your API keys
uvicorn main:app --host 0.0.0.0 --port 3011 --reload
```

### 4. Start the frontend

```bash
cd frontend
npm install
VITE_API_BASE=http://localhost:3011 npm run dev -- --port 3010
```

Open `http://localhost:3010`.

## LLM Providers

Set keys in `backend/.env`:

| Provider | Env Vars |
|----------|---------|
| DeepSeek | `DEEPSEEK_API_KEY`, `DEEPSEEK_API_BASE` |
| Kimi | `KIMI_API_KEY`, `KIMI_API_BASE` |
| Ollama (local) | `OLLAMA_API_BASE` |

## EntroFlow Device Resources

### File Layout

```
~/.entroflow/
├── assets/
│   ├── unixai/                    # ← installed by setup-entroflow.sh
│   │   ├── connector/             # HTTP API connector (local-only platform)
│   │   └── devices/unixai.robot/  # 旺达 robot driver
│   └── mihome/
│       └── devices/miaomiaoce.sensor_ht.t9/  # 温湿度计 driver
└── data/
    └── devices.json               # registered device records
```

### Registered Devices

| device_id | Name | Platform | Actions |
|-----------|------|----------|---------|
| `unixai:u098` | 旺达 | unixai | `speak`, `start_task`, `reset_task` |
| `mihome:blt.3.1...` | 米家智能温湿度计3 | mihome | status-only (temperature, humidity, battery) |

*The mihome connector itself is managed by EntroFlow (`entroflow connect mihome`). Only the device driver is stored in this repo.*

Customize via environment variables when running the setup script:

```bash
UNIXAI_DEVICE_NAME=我的机器人 \
UNIXAI_DEVICE_LOCATION=实验室 \
  bash scripts/setup-entroflow.sh
```

## ROS2 Humble (Docker)

For AGIBOT robot development on Apple Silicon:

```bash
# Build the SDK image (includes OpenCV, Ruckig, cv_bridge, ncurses, libcurl)
docker build -t ros2-humble-sdk -f Dockerfile.sdk-deps .

# Enter the environment
docker run -it --rm --net host -v $PWD:/workspace ros2-humble-sdk bash
source /opt/ros/humble/setup.bash
```

## License

MIT
