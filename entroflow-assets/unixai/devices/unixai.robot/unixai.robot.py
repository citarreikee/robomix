# -*- coding: utf-8 -*-
"""
UnixAI 机器人设备资源。
通过 HTTP API 控制 UnixAI 长程任务机器人（旺达 / U098）。
"""

DEVICE_INFO = {
    "model": "unixai.robot",
    "platform": "unixai",
    "display_name": "UnixAI Robot",
    "category": "robot",
}

ACTION_SPECS = [
    {
        "action": "start_task",
        "description": "开始一个长程任务。需要指定任务名和地点。",
        "args": "task, location",
        "range": "task: 递水/桌面清理, location: 神盾局",
    },
    {
        "action": "reset_task",
        "description": "重置任务状态（前端进度条复位，重新允许开始任务）。注意：此操作无后端调用，仅标记状态重置。",
        "args": "None",
        "range": "-",
    },
    {
        "action": "speak",
        "description": "让机器人通过 TTS 语音播报指定文字。",
        "args": "text",
        "range": "任意中英文文本",
    },
]

STATUS_FIELDS = [
    {"field": "robot_id", "description": "机器人标识符。", "type": "string"},
    {"field": "page_reachable", "description": "控制面板是否可达。", "type": "boolean"},
    {"field": "available_locations", "description": "当前控制面板上可选的地点列表。", "type": "list"},
    {"field": "available_tasks", "description": "当前控制面板上可选的任务列表（全局）。", "type": "list"},
    {"field": "tasks_by_location", "description": "按地点分组的任务列表。", "type": "object"},
]


class DeviceClass:
    def __init__(self, did, connector, record=None):
        self.did = did
        self.client = connector
        self.record = record or {}

    # ------------------------------------------------------------------
    # 状态查询
    # ------------------------------------------------------------------
    def query_status(self) -> str:
        """获取控制面板当前状态（地点/任务配置）。"""
        try:
            info = self.client.get_page_info()
        except Exception as exc:
            return f"page_reachable: false, error: {exc}"

        locs = info.get("locations", [])
        tasks = info.get("tasks", [])
        tbl = info.get("tasks_by_location", {})

        lines = [
            f"robot_id: {info.get('robot_id', self.did)}",
            f"page_reachable: {info.get('page_reachable', False)}",
            f"available_locations: {', '.join(l.get('label', l.get('value', '')) for l in locs) if locs else '未知（页面可能未完整加载）'}",
            f"available_tasks: {', '.join(t.get('label', t.get('value', '')) for t in tasks) if tasks else '未知'}",
        ]
        for loc, task_list in tbl.items():
            task_labels = ", ".join(t.get("label", t.get("value", "")) for t in task_list)
            lines.append(f"  {loc}: {task_labels}")
        return "\n".join(lines)

    # ------------------------------------------------------------------
    # 控制动作
    # ------------------------------------------------------------------
    def perform_action(self, action: str, **kwargs) -> str:
        if action == "start_task":
            return self._start_task(**kwargs)
        elif action == "reset_task":
            return self._reset_task(**kwargs)
        elif action == "speak":
            return self._speak(**kwargs)
        elif action == "query_status":
            return self.query_status()
        return f"unsupported action '{action}'"

    # ------------------------------------------------------------------
    # 具体实现
    # ------------------------------------------------------------------
    def _start_task(self, task: str = "", location: str = "", **kwargs) -> str:
        if not task:
            return "Error: task is required. 可用任务见 device_status 中的 available_tasks。"
        if not location:
            return "Error: location is required. 可用地点见 device_status 中的 available_locations。"

        # 尝试将中文标签映射为 value
        task_value = self._resolve_task_value(task)
        loc_value = self._resolve_location_value(location)

        try:
            result = self.client.notify_task("开始任务", task_value, loc_value)
            if result.get("success"):
                return f"任务已下发: task={task_value}, location={loc_value}。等待机器人执行（约6秒模型加载）。"
            return f"任务下发失败: {result.get('error', 'unknown error')}"
        except Exception as exc:
            return f"任务下发异常: {exc}"

    def _reset_task(self, **kwargs) -> str:
        # 前端 reset 没有后端 API 调用 — 仅清进度条、重新启用开始按钮
        return (
            "重置信号已发出。请确保机器人已完成当前任务并回到初始姿态，"
            "之后可使用 start_task 开始新任务。"
        )

    def _speak(self, text: str = "", **kwargs) -> str:
        if not text:
            return "Error: text is required."
        try:
            result = self.client.speak_tts(text)
            if result.get("success"):
                return f"TTS 播报已发送: \"{text}\""
            return f"TTS 发送失败: {result.get('error', 'unknown error')}"
        except Exception as exc:
            return f"TTS 请求异常: {exc}"

    # ------------------------------------------------------------------
    # 值解析辅助
    # ------------------------------------------------------------------
    def _resolve_task_value(self, task: str) -> str:
        """如果传入的是中文标签，尝试映射为内部 value。"""
        try:
            info = self.client.get_page_info()
        except Exception:
            return task
        for t in info.get("tasks", []):
            if task in (t.get("value"), t.get("label")):
                return t["value"]
        for task_list in info.get("tasks_by_location", {}).values():
            for t in task_list:
                if task in (t.get("value"), t.get("label")):
                    return t["value"]
        return task

    def _resolve_location_value(self, location: str) -> str:
        """如果传入的是中文标签，尝试映射为内部 value。"""
        try:
            info = self.client.get_page_info()
        except Exception:
            return location
        for loc in info.get("locations", []):
            if location in (loc.get("value"), loc.get("label")):
                return loc["value"]
        return location
