# UnixAI Robot (unixai.robot)

UnixAI 长程任务机器人设备资源。通过 HTTP API 控制机器人执行长程任务和 TTS 语音播报。

## 机器人信息

- 名称：旺达（Wanda）
- 型号：U098
- 控制面板：`http://192.168.0.38:5080/`

## 支持的动作

| 动作 | 说明 | 参数 |
|------|------|------|
| `start_task` | 开始长程任务 | task, location |
| `reset_task` | 重置任务状态 | 无 |
| `speak` | TTS 语音播报 | text |

## 可用任务/地点

（由控制面板页面动态提供，以 `device_status` 返回为准）

| 地点 | 任务 |
|------|------|
| 神盾局 | 递水、桌面清理 |
| 优理奇展厅 | 酒店清洁、机场安检 |
| 中新展厅 | 洗衣场景+桌面整理 |

## 技术实现

- 连接器通过 HTTP 与 Werkzeug 后端通信
- `/notify` → 下发任务
- `/tts` → 语音播报
- `reset_task` 为纯前端操作，无后端 API
