#!/usr/bin/env bash
# -*- coding: utf-8 -*-
set -euo pipefail

# ============================================================================
# Robomix EntroFlow 私有资源安装脚本
# 将仓库内的 UnixAI 平台资源链接到本机 EntroFlow 目录，并注册设备
# ============================================================================

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(dirname "$SCRIPT_DIR")"
ASSETS_SRC="$REPO_ROOT/entroflow-assets/unixai"
ENTROFLOW_HOME="${ENTROFLOW_HOME:-$HOME/.entroflow}"
ASSETS_DST="$ENTROFLOW_HOME/assets/unixai"

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

say()  { printf "%b\n" "$*"; }
ok()   { printf "${GREEN}✓${NC} %s\n" "$*"; }
warn() { printf "${YELLOW}⚠${NC} %s\n" "$*"; }
err()  { printf "${RED}✗${NC} %s\n" "$*"; }

# ---------------------------------------------------------------------------
# 1. 检查 EntroFlow 是否已安装
# ---------------------------------------------------------------------------
say "==> 检查 EntroFlow 安装状态 ..."

if command -v entroflow &>/dev/null; then
    ok "entroflow CLI 已安装: $(command -v entroflow)"
elif [ -f "$ENTROFLOW_HOME/cli.py" ]; then
    ok "entroflow 源码目录存在: $ENTROFLOW_HOME"
else
    err "EntroFlow 未安装。请先安装 EntroFlow："
    say "   curl -fsSL https://entroflow.ai/install | bash"
    say "   或 pip install entroflow"
    exit 1
fi

# ---------------------------------------------------------------------------
# 2. 链接/复制资源文件
# ---------------------------------------------------------------------------
say ""
say "==> 安装 UnixAI 平台资源 ..."

if [ ! -d "$ASSETS_SRC" ]; then
    err "找不到资源源目录: $ASSETS_SRC"
    exit 1
fi

# 使用符号链接（默认）或复制（macOS 某些配置下符号链接可能不被 EntroFlow 识别）
INSTALL_MODE="${ENTROFLOW_INSTALL_MODE:-copy}"

if [ "$INSTALL_MODE" = "symlink" ]; then
    say "   模式: 符号链接"
    rm -rf "$ASSETS_DST"
    ln -s "$ASSETS_SRC" "$ASSETS_DST"
else
    say "   模式: 复制"
    rm -rf "$ASSETS_DST"
    cp -r "$ASSETS_SRC" "$ASSETS_DST"
    # 删除可能混入的 pycache
    find "$ASSETS_DST" -name '__pycache__' -type d -exec rm -rf {} + 2>/dev/null || true
fi

ok "资源已安装到: $ASSETS_DST"

# 验证关键文件
for f in \
    "connector/client.py" \
    "connector/manifest.json" \
    "connector/unixai_devices.json" \
    "devices/unixai.robot/unixai.robot.py"; do
    if [ -f "$ASSETS_DST/$f" ]; then
        ok "  $f"
    else
        err "  缺失: $f"
    fi
done

# ---------------------------------------------------------------------------
# 3. 注册设备
# ---------------------------------------------------------------------------
say ""
say "==> 注册设备"

# 设备信息（按需修改）
DEVICE_DID="${UNIXAI_DEVICE_DID:-u098}"
DEVICE_MODEL="${UNIXAI_DEVICE_MODEL:-unixai.robot}"
DEVICE_PLATFORM="${UNIXAI_DEVICE_PLATFORM:-unixai}"
DEVICE_NAME="${UNIXAI_DEVICE_NAME:-旺达}"
DEVICE_LOCATION="${UNIXAI_DEVICE_LOCATION:-神盾局}"
DEVICE_REMARK="${UNIXAI_DEVICE_REMARK:-UnixAI 长程任务机器人 U098, 控制面板 http://192.168.0.38:5080}"

say "   did      = $DEVICE_DID"
say "   model    = $DEVICE_MODEL"
say "   platform = $DEVICE_PLATFORM"
say "   name     = $DEVICE_NAME"
say "   location = $DEVICE_LOCATION"

if command -v entroflow &>/dev/null; then
    # 优先用 entroflow CLI 注册
    entroflow setup \
        --platform "$DEVICE_PLATFORM" \
        --did "$DEVICE_DID" \
        --model "$DEVICE_MODEL" \
        --name "$DEVICE_NAME" \
        --location "$DEVICE_LOCATION" \
        --remark "$DEVICE_REMARK" \
        2>&1 || warn "entroflow setup 失败，尝试直接写入 devices.json ..."
fi

# 兜底：直接写入 devices.json
DEVICES_FILE="$ENTROFLOW_HOME/data/devices.json"
DEVICE_ID="${DEVICE_PLATFORM}:${DEVICE_DID}"

if [ -f "$DEVICES_FILE" ]; then
    # 检查是否已存在
    if python3 -c "
import json, sys
devices = json.load(open('$DEVICES_FILE'))
ids = [d.get('device_id') for d in devices]
sys.exit(0 if '$DEVICE_ID' in ids else 1)
" 2>/dev/null; then
        ok "设备已注册: $DEVICE_ID"
    else
        # 用 Python API 注册
        python3 -c "
import sys
sys.path.insert(0, '$ENTROFLOW_HOME')
from core import store
store.register(
    did='$DEVICE_DID',
    model='$DEVICE_MODEL',
    platform='$DEVICE_PLATFORM',
    name='$DEVICE_NAME',
    location='$DEVICE_LOCATION',
    remark='$DEVICE_REMARK',
)
print('registered: $DEVICE_ID')
" 2>&1 && ok "设备已注册: $DEVICE_ID" || warn "设备注册失败，请手动运行: entroflow setup ..."
    fi
else
    # 首次注册
    mkdir -p "$(dirname "$DEVICES_FILE")"
    python3 -c "
import sys
sys.path.insert(0, '$ENTROFLOW_HOME')
from core import store
store.register(
    did='$DEVICE_DID',
    model='$DEVICE_MODEL',
    platform='$DEVICE_PLATFORM',
    name='$DEVICE_NAME',
    location='$DEVICE_LOCATION',
    remark='$DEVICE_REMARK',
)
print('registered: $DEVICE_ID')
" 2>&1 && ok "设备已注册: $DEVICE_ID" || warn "设备注册失败"
fi

# ---------------------------------------------------------------------------
# 4. 完成
# ---------------------------------------------------------------------------
say ""
say "============================================"
say "  EntroFlow 私有资源安装完成"
say "============================================"
say ""
say "验证安装:"
say "  entroflow device-search all"
say ""
say "如果需要修改设备信息（名称/位置/remark），编辑此脚本顶部的环境变量"
say "或在运行时传入:"
say "  UNIXAI_DEVICE_NAME=我的机器人 bash $0"
