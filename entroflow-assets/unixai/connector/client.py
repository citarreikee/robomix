# -*- coding: utf-8 -*-
"""
UnixAI 机器人平台连接器。
通过 HTTP 与 UnixAI 长程任务控制面板通信（默认 http://192.168.0.38:5080）。
"""
import os
import re
from typing import Any, Dict, List, Optional

import httpx

_DEFAULT_BASE_URL = "http://192.168.0.38:5080"


def _base_url() -> str:
    return os.environ.get("UNIXAI_BASE_URL", _DEFAULT_BASE_URL).rstrip("/")


def _client() -> httpx.Client:
    return httpx.Client(timeout=10.0)


# ---------------------------------------------------------------------------
# 发现
# ---------------------------------------------------------------------------
def list_devices() -> List[Dict[str, Any]]:
    """列出 UnixAI 控制面板上可用的机器人设备。"""
    url = f"{_base_url()}/"
    try:
        with _client() as c:
            resp = c.get(url)
            resp.raise_for_status()
        html = resp.text

        # 从页面标题提取机器人 ID
        robot_id = "u098"
        title_match = re.search(r"Robot:\s*(\w+)", html)
        if title_match:
            robot_id = title_match.group(1).lower()

        # 提取页面内置的地点/任务配置
        locations = _extract_json_list(html, "locations")
        tasks = _extract_json_list(html, "tasks")
        tasks_by_location = _extract_json_object(html, "tasks_by_location")

        return [
            {
                "did": robot_id,
                "model": "unixai.robot",
                "name": f"UnixAI Robot {robot_id.upper()} (旺达)",
                "platform": "unixai",
                "locations": locations,
                "tasks": tasks,
                "tasks_by_location": tasks_by_location,
            }
        ]
    except Exception as exc:
        raise RuntimeError(f"无法连接 UnixAI 控制面板 ({url}): {exc}")


# ---------------------------------------------------------------------------
# 控制 API
# ---------------------------------------------------------------------------
def notify_task(module: str, task: str, location: str) -> Dict[str, Any]:
    """通知后端开始任务。对应 POST /notify"""
    url = f"{_base_url()}/notify"
    payload = {"module": module, "task": task, "location": location}
    with _client() as c:
        resp = c.post(url, json=payload)
        resp.raise_for_status()
        return resp.json()


def speak_tts(text: str) -> Dict[str, Any]:
    """文字转语音播报。对应 POST /tts"""
    url = f"{_base_url()}/tts"
    payload = {"text": text}
    with _client() as c:
        resp = c.post(url, json=payload)
        resp.raise_for_status()
        return resp.json()


def get_page_info() -> Dict[str, Any]:
    """获取控制面板页面信息（地点、任务配置）。对应 GET /"""
    url = f"{_base_url()}/"
    with _client() as c:
        resp = c.get(url)
        resp.raise_for_status()
    html = resp.text
    robot_id = "u098"
    title_match = re.search(r"Robot:\s*(\w+)", html)
    if title_match:
        robot_id = title_match.group(1).lower()
    return {
        "robot_id": robot_id,
        "locations": _extract_json_list(html, "locations"),
        "tasks": _extract_json_list(html, "tasks"),
        "tasks_by_location": _extract_json_object(html, "tasks_by_location"),
        "page_reachable": True,
    }


# ---------------------------------------------------------------------------
# HTML 解析辅助
# ---------------------------------------------------------------------------
def _extract_json_list(html: str, key: str) -> List[Dict[str, str]]:
    """从页面 JS 中提取 UI_OPTIONS 里的数组字段。"""
    pattern = rf'"{key}"\s*:\s*(\[[^\]]*\])'
    match = re.search(pattern, html, re.DOTALL)
    if not match:
        return []
    raw = match.group(1)
    items = re.findall(r'\{"value"\s*:\s*"([^"]*)"\s*,\s*"label"\s*:\s*"([^"]*)"\}', raw)
    return [{"value": v, "label": l} for v, l in items]


def _extract_json_object(html: str, key: str) -> Dict[str, List[Dict[str, str]]]:
    """从页面 JS 中提取 UI_OPTIONS 里的对象字段（如 tasks_by_location）。"""
    pattern = rf'"{key}"\s*:\s*(\{{[^}}]*(?:\{{[^}}]*\}}[^}}]*)*\}})'
    match = re.search(pattern, html, re.DOTALL)
    if not match:
        return {}
    raw = match.group(1)
    result: Dict[str, List[Dict[str, str]]] = {}
    # 匹配每个 location key
    entries = re.findall(
        r'"([^"]+)"\s*:\s*\[([^\]]*)\]',
        raw, re.DOTALL
    )
    for loc, tasks_raw in entries:
        items = re.findall(r'\{"value"\s*:\s*"([^"]*)"\s*,\s*"label"\s*:\s*"([^"]*)"\}', tasks_raw)
        result[loc] = [{"value": v, "label": l} for v, l in items]
    return result
