#!/usr/bin/env bash
# -*- coding: utf-8 -*-
set -euo pipefail

# ============================================================================
# Robomix EntroFlow 私有资源安装脚本
# 将仓库内的所有 EntroFlow 资产安装到 ~/.entroflow/assets/
# ============================================================================

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(dirname "$SCRIPT_DIR")"
SRC_ROOT="$REPO_ROOT/entroflow-assets"
ENTROFLOW_HOME="${ENTROFLOW_HOME:-$HOME/.entroflow}"
INSTALL_MODE="${ENTROFLOW_INSTALL_MODE:-copy}"

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
    ok "entroflow CLI: $(command -v entroflow)"
elif [ -f "$ENTROFLOW_HOME/cli.py" ]; then
    ok "entroflow 源码: $ENTROFLOW_HOME"
else
    err "EntroFlow 未安装。请先安装 EntroFlow 再运行本脚本。"
    exit 1
fi

# ---------------------------------------------------------------------------
# 2. 安装所有平台资源
# ---------------------------------------------------------------------------
say ""
say "==> 安装私有 EntroFlow 资源 ..."

if [ ! -d "$SRC_ROOT" ]; then
    err "找不到资源目录: $SRC_ROOT"
    exit 1
fi

INSTALLED_PLATFORMS=()

for platform_dir in "$SRC_ROOT"/*/; do
    platform="$(basename "$platform_dir")"
    dst="$ENTROFLOW_HOME/assets/$platform"

    # 跳过非目录
    [ ! -d "$platform_dir" ] && continue

    if [ "$INSTALL_MODE" = "symlink" ]; then
        say "  链接: $platform → $dst"
        rm -rf "$dst"
        ln -s "$(cd "$platform_dir" && pwd)" "$dst"
    else
        say "  复制: $platform → $dst"
        mkdir -p "$dst"
        # 复制 connector（如果存在）
        if [ -d "$platform_dir/connector" ]; then
            rm -rf "$dst/connector"
            cp -r "$platform_dir/connector" "$dst/connector"
        fi
        # 复制 devices（如果存在）
        if [ -d "$platform_dir/devices" ]; then
            rm -rf "$dst/devices"
            cp -r "$platform_dir/devices" "$dst/devices"
        fi
        # 清理 pycache
        find "$dst" -name '__pycache__' -type d -exec rm -rf {} + 2>/dev/null || true
    fi

    INSTALLED_PLATFORMS+=("$platform")

    # 列出已安装的设备模型
    for device_dir in "$platform_dir"/devices/*/; do
        [ -d "$device_dir" ] || continue
        model="$(basename "$device_dir")"
        ok "  device: $platform / $model"
    done
done

if [ ${#INSTALLED_PLATFORMS[@]} -eq 0 ]; then
    warn "未安装任何资源"
else
    ok "已安装平台: ${INSTALLED_PLATFORMS[*]}"
fi

# ---------------------------------------------------------------------------
# 3. 注册设备
# ---------------------------------------------------------------------------
say ""
say "==> 注册设备 ..."

_register() {
    local did="$1" model="$2" platform="$3" name="$4" location="$5" remark="$6"
    local device_id="${platform}:${did}"
    local devices_file="$ENTROFLOW_HOME/data/devices.json"

    # 检查是否已注册
    if [ -f "$devices_file" ]; then
        if python3 -c "
import json, sys
devices = json.load(open('$devices_file'))
ids = [d.get('device_id') for d in devices]
sys.exit(0 if '$device_id' in ids else 1)
" 2>/dev/null; then
            ok "已注册: $device_id ($name)"
            return
        fi
    fi

    # 调用 EntroFlow Python API 注册
    mkdir -p "$(dirname "$devices_file")"
    if python3 -c "
import sys
sys.path.insert(0, '$ENTROFLOW_HOME')
from core import store
store.register(
    did='$did',
    model='$model',
    platform='$platform',
    name='$name',
    location='$location',
    remark='$remark',
)
print('ok')
" 2>&1; then
        ok "注册成功: $device_id ($name)"
    else
        warn "注册失败: $device_id，请手动运行 entroflow setup"
    fi
}

# ---- UnixAI 机器人 ----
_register \
    "${UNIXAI_DID:-u098}" \
    "${UNIXAI_MODEL:-unixai.robot}" \
    "unixai" \
    "${UNIXAI_NAME:-旺达}" \
    "${UNIXAI_LOCATION:-神盾局}" \
    "UnixAI 长程任务机器人 U098, 控制面板 http://192.168.0.38:5080"

# ---- 米家温湿度计 ----
_register \
    "${MIHOME_SENSOR_DID:-blt.3.1pa223skt0k00}" \
    "${MIHOME_SENSOR_MODEL:-miaomiaoce.sensor_ht.t9}" \
    "mihome" \
    "${MIHOME_SENSOR_NAME:-米家智能温湿度计3}" \
    "${MIHOME_SENSOR_LOCATION:-神盾局}" \
    "神盾局温度传感器"

# ---------------------------------------------------------------------------
# 4. 完成
# ---------------------------------------------------------------------------
say ""
say "============================================"
say "  EntroFlow 私有资源安装完成"
say "============================================"
say ""
say "验证: 在 Claude Code 或 MCP 客户端中调用 device_search('all')"
say ""
say "自定义设备信息:"
say "  UNIXAI_NAME=我的机器人 MIHOME_SENSOR_LOCATION=实验室 bash $0"
