# Robomix

AI chat panel with LLM streaming, ReAct tool calling, and EntroFlow device control for physical robots and IoT devices.

## Architecture

```
┌──────────────┐     HTTP/SSE      ┌──────────────┐     CLI/MCP     ┌────────────┐
│   frontend   │ ◄──────────────► │   backend    │ ◄─────────────► │ EntroFlow  │
│  React/Vite  │                   │  FastAPI     │                 │  Runtime   │
│  :3010       │                   │  :3011       │                 └────────────┘
└──────────────┘                   └──────────────┘
```

## Prerequisites

| Dependency | How to check | Install |
|-----------|-------------|---------|
| Python ≥ 3.10 | `python3 --version` | [python.org](https://python.org) / pyenv |
| Node.js ≥ 18 | `node --version` | [nodejs.org](https://nodejs.org) / nvm |
| EntroFlow | `entroflow --help` | `curl -fsSL https://entroflow.ai/install \| bash` |

## Quick Start (from zero)

```bash
# 1. Clone
git clone git@github.com:citarreikee/robomix.git
cd robomix

# 2. Install EntroFlow (if not already)
curl -fsSL https://entroflow.ai/install | bash

# 3. Install private EntroFlow resources & register devices
bash scripts/setup-entroflow.sh

# 4. Backend
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
# → Edit .env with your API keys ←
uvicorn main:app --host 0.0.0.0 --port 3011 --reload

# 5. Frontend (new terminal)
cd frontend
npm install
VITE_API_BASE=http://localhost:3011 npm run dev -- --port 3010
```

Open `http://localhost:3010`.

## What `setup-entroflow.sh` Does

The script installs local-only EntroFlow resources included in this repo:

| Resource | Type | Description |
|----------|------|-------------|
| `unixai` | Platform + Device | UnixAI 旺达 robot (HTTP API at `192.168.0.38:5080`) |
| `miaomiaoce.sensor_ht.t9` | Device only | 米家智能温湿度计3 sensor driver |

It copies `entroflow-assets/` → `~/.entroflow/assets/` and registers devices in `~/.entroflow/data/devices.json`.

> **For your own devices:** edit the `_register` calls at the bottom of the script with your device DIDs, names, and locations. The Mi Home sensor DID is hardware-specific — run `entroflow list-devices --platform mihome` to find yours.

### Customizing device info

```bash
UNIXAI_NAME=我的机器人 \
UNIXAI_LOCATION=实验室 \
MIHOME_SENSOR_DID=your-did-here \
  bash scripts/setup-entroflow.sh
```

## LLM Providers

Set at least one key in `backend/.env`:

| Provider | Env Vars | Sign up |
|----------|---------|---------|
| DeepSeek | `DEEPSEEK_API_KEY` | [platform.deepseek.com](https://platform.deepseek.com) |
| Kimi | `KIMI_API_KEY` | [platform.moonshot.cn](https://platform.moonshot.cn) |
| Ollama | `OLLAMA_API_BASE` | local, `ollama serve` |

## Device Control

Once running, you can control devices through the chat panel or directly via EntroFlow MCP tools:

```
device_search("all")
device_status("unixai:u098")
device_control("unixai:u098", {"action": "speak", "args": {"text": "你好"}})
```

## Repo Structure

```
robomix/
├── entroflow-assets/              # Private EntroFlow resources
│   ├── unixai/
│   │   ├── connector/             # HTTP connector (local-only platform)
│   │   └── devices/unixai.robot/  # 旺达 robot driver
│   └── mihome/
│       └── devices/miaomiaoce.sensor_ht.t9/  # 温湿度计 driver
├── scripts/
│   └── setup-entroflow.sh         # One-click resource install
├── backend/                       # FastAPI + ReAct tool calling
│   ├── main.py                    # Entry point
│   ├── providers/                 # LLM adapters (DeepSeek, Kimi, Ollama)
│   ├── services/                  # Chat orchestration, EntroFlow bridge
│   └── tools/                     # device_search, device_status, device_control
├── frontend/                      # React 19 + Vite chat UI
├── robot-sdk/                      # AGIBOT 灵犀 X2 AimDK v0.9.0
│   └── src/                        # aimdk_msgs, ruckig, examples, py_examples
├── Dockerfile.ros2                # ROS2 Humble ARM64 base image
├── Dockerfile.sdk-deps            # base + deps + SDK compiled with colcon
└── README.md
```

## ROS2 Humble + AGIBOT SDK (Docker)

For AGIBOT Lingxi X2 robot development on Apple Silicon:

```bash
# Build (includes AGIBOT AimDK v0.9.0)
docker build -t ros2-humble-sdk -f Dockerfile.sdk-deps .

# Run with network access to reach the robot
docker run -it --rm --net host -v $PWD:/workspace ros2-humble-sdk bash

# Inside the container, both ROS2 and SDK are ready:
source /opt/ros/humble/setup.bash
source /workspace/robot-sdk/install/setup.bash
ros2 pkg list | grep aimdk   # aimdk_msgs, examples, py_examples, ruckig
```

### SDK Executables (22 C++ / 23 Python)

| Category | Nodes |
|----------|-------|
| **HAL** | echo_camera_rgbd, echo_camera_stereo, echo_camera_head_rear, echo_imu_data, echo_lidar_data, echo_head_touch_sensor, motocontrol, hand_control, omnihand_control, take_photo |
| **MC** | mc_locomotion_velocity, preset_motion_client, get_mc_action, set_mc_action, get_current_input_source, set_mc_input_source, keyboard |
| **Interaction** | play_tts, play_media, play_video, play_emoji, play_lights, mic_receiver |

## License

MIT
