from __future__ import annotations

import importlib
import json
import re
import shlex
import shutil
import subprocess
import sys
import threading
import time
from dataclasses import dataclass
from importlib import util as importlib_util
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

from config import settings


ALL_QUERY_TOKENS = {"all", "*", "all_devices", "all-devices"}
ENTROFLOW_HOME = Path.home() / ".entroflow"
ENTROFLOW_STORE_PATH = ENTROFLOW_HOME / "data" / "devices.json"

_STORE_MODULE: Any = None
_LOADER_MODULE: Any = None
_CONFIG_MODULE: Any = None
_DOWNLOADER_MODULE: Any = None
_SETUP_TOOLS_MODULE: Any = None
_RESOURCE_SIGNATURE = ""
_RESOURCE_SIGNATURE_CHECKED_AT = 0.0
_CONNECT_POLLERS: Dict[str, threading.Thread] = {}
_CONNECT_POLL_RESULTS: Dict[str, Dict[str, Any]] = {}
_CONNECT_POLLERS_LOCK = threading.Lock()


@dataclass
class EntroFlowActionResult:
    action: str
    ok: bool
    message: str
    args: Dict[str, Any]


def _safe_str(value: Any) -> str:
    return "" if value is None else str(value).strip()


def _normalize_text(value: Any) -> str:
    text = _safe_str(value).lower()
    return re.sub(r"[\W_]+", "", text, flags=re.UNICODE) if text else ""


def _code_root() -> Path:
    if (ENTROFLOW_HOME / "core" / "loader.py").exists():
        return ENTROFLOW_HOME
    raise RuntimeError("EntroFlow runtime was not found at ~/.entroflow. Install EntroFlow first, then retry.")


def _load_module(module_name: str, path: Path) -> Any:
    spec = importlib_util.spec_from_file_location(module_name, str(path))
    if not spec or not spec.loader:
        raise ImportError(f"Cannot load module: {path}")
    module = importlib_util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


def _import_entroflow_module(module_name: str) -> Any:
    root = str(_code_root())
    inserted = False
    shadowed_modules: Dict[str, Any] = {}
    top_level = module_name.split(".", 1)[0]
    if root not in sys.path:
        sys.path.insert(0, root)
        inserted = True
    for name in {top_level, "cli", "core", "tools"}:
        module = sys.modules.get(name)
        module_file = Path(str(getattr(module, "__file__", ""))).resolve() if module else None
        if module is not None and (module_file is None or not str(module_file).startswith(root)):
            shadowed_modules[name] = module
            sys.modules.pop(name, None)
    try:
        return importlib.import_module(module_name)
    finally:
        for name, module in shadowed_modules.items():
            if name not in sys.modules:
                sys.modules[name] = module
        if inserted:
            try:
                sys.path.remove(root)
            except ValueError:
                pass


def _store_module() -> Any:
    global _STORE_MODULE
    if _STORE_MODULE is None:
        _STORE_MODULE = _load_module("robomix_entroflow_core_store", _code_root() / "core" / "store.py")
    return _STORE_MODULE


def _loader_module() -> Any:
    global _LOADER_MODULE
    if _LOADER_MODULE is None:
        _LOADER_MODULE = _load_module("robomix_entroflow_core_loader", _code_root() / "core" / "loader.py")
    return _LOADER_MODULE


def _config_module() -> Any:
    global _CONFIG_MODULE
    if _CONFIG_MODULE is None:
        _CONFIG_MODULE = _import_entroflow_module("core.config")
    return _CONFIG_MODULE


def _downloader_module() -> Any:
    global _DOWNLOADER_MODULE
    if _DOWNLOADER_MODULE is None:
        _DOWNLOADER_MODULE = _import_entroflow_module("core.downloader")
    return _DOWNLOADER_MODULE


def _setup_tools_module() -> Any:
    global _SETUP_TOOLS_MODULE
    if _SETUP_TOOLS_MODULE is None:
        _SETUP_TOOLS_MODULE = _import_entroflow_module("tools.setup")
    return _SETUP_TOOLS_MODULE


def _load_raw_devices() -> List[Dict[str, Any]]:
    try:
        return [dict(item) for item in _store_module().load() if isinstance(item, dict)]
    except Exception:
        if not ENTROFLOW_STORE_PATH.exists():
            return []
        try:
            data = json.loads(ENTROFLOW_STORE_PATH.read_text(encoding="utf-8"))
            return [dict(item) for item in data if isinstance(item, dict)]
        except Exception:
            return []


def _file_signature(path: Path) -> str:
    try:
        stat = path.stat()
        return f"{path}:{stat.st_mtime_ns}:{stat.st_size}"
    except OSError:
        return f"{path}:missing"


def _runtime_resource_signature() -> str:
    records = _load_raw_devices()
    paths = [ENTROFLOW_HOME / "config.json", ENTROFLOW_STORE_PATH, ENTROFLOW_HOME / "assets" / "catalog.json"]
    try:
        root = _code_root()
        paths.extend([root / "core" / "loader.py", root / "core" / "store.py"])
    except Exception:
        pass
    for record in records:
        platform = _safe_str(record.get("platform"))
        model = _safe_str(record.get("model"))
        if platform and model:
            device_dir = ENTROFLOW_HOME / "assets" / platform / "devices" / model
            paths.extend(device_dir.glob("*.py") if device_dir.exists() else [device_dir / f"{model}.py"])
    return "|".join(sorted(_file_signature(path) for path in paths))


def clear_runtime_caches() -> None:
    global _STORE_MODULE, _LOADER_MODULE, _CONFIG_MODULE, _DOWNLOADER_MODULE, _SETUP_TOOLS_MODULE
    loader = _LOADER_MODULE
    if loader is not None:
        cache = getattr(loader, "_module_cache", None)
        if isinstance(cache, dict):
            cache.clear()
        clear_connector_cache = getattr(loader, "clear_connector_cache", None)
        if callable(clear_connector_cache):
            try:
                clear_connector_cache()
            except Exception:
                pass
    _STORE_MODULE = None
    _LOADER_MODULE = None
    _CONFIG_MODULE = None
    _DOWNLOADER_MODULE = None
    _SETUP_TOOLS_MODULE = None
    sys.modules.pop("robomix_entroflow_core_store", None)
    sys.modules.pop("robomix_entroflow_core_loader", None)


def _refresh_runtime_if_changed(*, force: bool = False) -> None:
    global _RESOURCE_SIGNATURE, _RESOURCE_SIGNATURE_CHECKED_AT
    now = time.monotonic()
    if not force and now - _RESOURCE_SIGNATURE_CHECKED_AT < 1.0:
        return
    _RESOURCE_SIGNATURE_CHECKED_AT = now
    try:
        signature = _runtime_resource_signature()
    except Exception:
        if force:
            clear_runtime_caches()
        return
    if force or signature != _RESOURCE_SIGNATURE:
        clear_runtime_caches()
        _RESOURCE_SIGNATURE = signature


def _device_display_name(record: Dict[str, Any]) -> str:
    return (
        _safe_str(record.get("name"))
        or _safe_str(record.get("name_cn"))
        or _safe_str(record.get("name_en"))
        or _safe_str(record.get("remark"))
        or _safe_str(record.get("device_id"))
        or "unknown-device"
    )


def _find_raw_device(device_id: str) -> Optional[Dict[str, Any]]:
    target = _safe_str(device_id)
    for record in _load_raw_devices():
        if _safe_str(record.get("device_id")) == target:
            return record
    return None


def resolve_device_id(device_id: str) -> str:
    _refresh_runtime_if_changed()
    target = _safe_str(device_id)
    if _find_raw_device(target):
        return target
    matches = [_safe_str(record.get("device_id")) for record in _load_raw_devices() if _safe_str(record.get("did")) == target]
    matches = [item for item in matches if item]
    return matches[0] if len(matches) == 1 else target


def _load_device_module(record: Dict[str, Any]) -> Any:
    _refresh_runtime_if_changed()
    platform = _safe_str(record.get("platform"))
    model = _safe_str(record.get("model"))
    if not platform or not model:
        raise ValueError("EntroFlow device record is missing platform or model.")
    return _loader_module().load_device_class(platform, model)


def _create_device_instance(record: Dict[str, Any]) -> Any:
    _refresh_runtime_if_changed()
    return _loader_module().create_device_instance(record)


def _raw_action_specs(record: Dict[str, Any]) -> List[Dict[str, Any]]:
    try:
        module = _load_device_module(record)
    except Exception:
        return []
    specs = getattr(module, "ACTION_SPECS", []) or []
    normalized: List[Dict[str, Any]] = []
    for spec in specs:
        if not isinstance(spec, dict):
            continue
        action = _safe_str(spec.get("action"))
        if action and action != "query_status":
            row = dict(spec)
            row["action"] = action
            normalized.append(row)
    if normalized:
        return normalized
    for action in getattr(module, "SUPPORTED_ACTIONS", []) or []:
        action_name = _safe_str(action)
        if action_name and action_name != "query_status":
            normalized.append({"action": action_name, "description": "", "args": "None", "range": "-"})
    return normalized


def get_action_capabilities(device_id: str) -> Dict[str, Any]:
    resolved = resolve_device_id(device_id)
    record = _find_raw_device(resolved)
    if not record:
        raise ValueError(f"Device '{device_id}' was not found in EntroFlow runtime.")
    specs = _raw_action_specs(record)
    supported = [_safe_str(spec.get("action")) for spec in specs if _safe_str(spec.get("action"))]
    if "set_fan_level" in supported and "set_fan_speed" not in supported:
        specs.append({"action": "set_fan_speed", "description": "Alias for set_fan_level.", "args": "fan_speed", "range": "low / medium / high / auto"})
        supported.append("set_fan_speed")
    return {"device_id": resolved, "action_specs": specs, "supported_actions": supported}


def list_devices() -> List[Dict[str, Any]]:
    _refresh_runtime_if_changed()
    devices = []
    for record in _load_raw_devices():
        device_id = _safe_str(record.get("device_id"))
        devices.append(
            {
                **record,
                "device_id": device_id,
                "entity_id": device_id,
                "source": "entroflow",
                "name": _device_display_name(record),
                "platform": _safe_str(record.get("platform")),
                "location": _safe_str(record.get("location")),
                "remark": _safe_str(record.get("remark")),
                "model": _safe_str(record.get("model")),
                "did": _safe_str(record.get("did")),
            }
        )
    return devices


def _query_device_status(record: Dict[str, Any]) -> str:
    device = _create_device_instance(record)
    if hasattr(device, "query_status"):
        return str(device.query_status())
    if hasattr(device, "perform_action"):
        return str(device.perform_action("query_status"))
    raise RuntimeError("device cannot report status")


def list_device_cards() -> List[Dict[str, Any]]:
    _refresh_runtime_if_changed()
    cards: List[Dict[str, Any]] = []
    for record in _load_raw_devices():
        device_id = _safe_str(record.get("device_id"))
        try:
            status = _query_device_status(record)
            status_ok = _status_is_ok(status)
        except Exception as exc:
            status = f"状态不可用：{exc}"
            status_ok = False
        cards.append(
            {
                "name": _device_display_name(record),
                "alias": _safe_str(record.get("alias")),
                "platform": _safe_str(record.get("platform")),
                "source": "entroflow",
                "remark": _safe_str(record.get("remark")),
                "status_text": status,
                "status_ok": status_ok,
            }
        )
    return cards


def _match_score(record: Dict[str, Any], query_normalized: str) -> int:
    best = 0
    for key in ("device_id", "did", "name", "name_cn", "name_en", "location", "remark", "model", "platform"):
        term = _normalize_text(record.get(key))
        if not term:
            continue
        if term == query_normalized:
            return 100
        if query_normalized in term:
            best = max(best, 80)
        if term in query_normalized:
            best = max(best, 60)
    return best


def _format_action_specs(specs: Sequence[Dict[str, Any]]) -> List[str]:
    if not specs:
        return ["    supported_actions: none (status only or driver metadata unavailable)"]
    lines = ["    supported_actions:"]
    for spec in specs:
        action = _safe_str(spec.get("action"))
        if action:
            lines.append(f"      - {action}: {_safe_str(spec.get('description')) or '-'} (args: {_safe_str(spec.get('args')) or 'None'}, range: {_safe_str(spec.get('range')) or '-'})")
    return lines


def _format_search_result(records: Sequence[Dict[str, Any]], query: str, *, truncated: bool = False) -> str:
    if not records:
        return f"No registered EntroFlow runtime devices matched '{query}'. Set up the device in EntroFlow first."
    lines = ["Found {0} registered EntroFlow device(s):".format(len(records)), "Use exact device_id values. Put action parameters under action.args.", ""]
    for index, record in enumerate(records, start=1):
        lines.append(f"[{index}] {_device_display_name(record)}")
        lines.append(f"    device_id : {_safe_str(record.get('device_id'))}")
        lines.append(f"    model     : {_safe_str(record.get('model')) or '?'}")
        lines.append(f"    platform  : {_safe_str(record.get('platform')) or '?'}")
        lines.append(f"    location  : {_safe_str(record.get('location')) or '?'}")
        lines.append(f"    remark    : {_safe_str(record.get('remark')) or '?'}")
        lines.extend(_format_action_specs(_raw_action_specs(record)))
        lines.append("")
    if truncated:
        lines.append("More devices matched; increase top_k or use query='all'.")
    return "\n".join(lines).strip()


def search_device_capabilities(query: str, top_k: int = 5) -> str:
    _refresh_runtime_if_changed()
    devices = _load_raw_devices()
    if not devices:
        return "No devices are registered in EntroFlow runtime. Use entroflow_cli to connect a platform and setup devices first."
    raw_query = _safe_str(query)
    lowered = raw_query.lower()
    normalized = _normalize_text(raw_query)
    if lowered in ALL_QUERY_TOKENS or normalized in ALL_QUERY_TOKENS:
        return _format_search_result(devices, "all")
    if not normalized:
        return "Error: query is required. Use a registered name, location, remark, device_id, or 'all'."
    scored = [(score, record) for record in devices if (score := _match_score(record, normalized)) > 0]
    scored.sort(key=lambda item: (-item[0], _device_display_name(item[1]).lower()))
    safe_top_k = max(1, min(int(top_k or 5), 20))
    matches = [record for _, record in scored[:safe_top_k]]
    return _format_search_result(matches, raw_query, truncated=len(scored) > len(matches))


def get_registered_device_names() -> List[str]:
    names = []
    seen = set()
    for record in _load_raw_devices():
        name = _device_display_name(record)
        if name not in seen:
            names.append(name)
            seen.add(name)
    return names


def build_registered_devices_system_prompt() -> str:
    names = get_registered_device_names()
    if not names:
        return "No devices are currently registered in EntroFlow. If the user asks for device control, help them connect/setup via entroflow_cli."
    return (
        "Currently registered EntroFlow devices: "
        + ", ".join(names)
        + ". Always call device_search for exact device_id and supported_actions before device_status or device_control."
    )


def _normalize_actions(actions: Any) -> List[Any]:
    if actions is None:
        return []
    if isinstance(actions, str):
        try:
            return _normalize_actions(json.loads(actions))
        except json.JSONDecodeError:
            return [{"action": actions, "args": {}}]
    if isinstance(actions, dict):
        return [actions]
    if isinstance(actions, (list, tuple)):
        return list(actions)
    return []


def _entry_to_dict(entry: Any) -> Optional[Dict[str, Any]]:
    if isinstance(entry, dict):
        return dict(entry)
    if isinstance(entry, str):
        try:
            decoded = json.loads(entry)
            return decoded if isinstance(decoded, dict) else {"action": entry, "args": {}}
        except json.JSONDecodeError:
            return {"action": entry, "args": {}}
    return None


def _parse_args(value: Any) -> Optional[Dict[str, Any]]:
    if value is None:
        return {}
    if isinstance(value, dict):
        return dict(value)
    if isinstance(value, str):
        try:
            decoded = json.loads(value)
            return dict(decoded) if isinstance(decoded, dict) else None
        except json.JSONDecodeError:
            return None
    return None


def _normalize_action_for_runtime(record: Dict[str, Any], action: str, args: Dict[str, Any]) -> tuple[str, Dict[str, Any]]:
    runtime_action = _safe_str(action)
    runtime_args = dict(args)
    supported = set(get_action_capabilities(_safe_str(record.get("device_id"))).get("supported_actions") or [])
    if runtime_action == "set_fan_speed" and "set_fan_level" in supported:
        runtime_action = "set_fan_level"
    if "channels" in runtime_args and "channel" not in runtime_args:
        runtime_args["channel"] = runtime_args["channels"]
    if runtime_action == "set_fan_level":
        if "fan_speed" in runtime_args and "fan_level" not in runtime_args:
            runtime_args["fan_level"] = runtime_args["fan_speed"]
        if "level" in runtime_args and "fan_level" not in runtime_args:
            runtime_args["fan_level"] = runtime_args["level"]
    if runtime_action == "set_mode" and isinstance(runtime_args.get("mode"), str):
        mode_map = {"fan_only": "fan", "cooling": "cool", "heating": "heat"}
        runtime_args["mode"] = mode_map.get(runtime_args["mode"].strip().lower(), runtime_args["mode"].strip().lower())
    return runtime_action, runtime_args


def _result_is_error(result: str) -> bool:
    text = _safe_str(result)
    lowered = text.lower()
    if "status=pending" in lowered and ("public_url=" in lowered or "type=scan_qr" in lowered):
        return False
    return (
        not text
        or lowered.startswith(("error:", "failed", "unknown", "missing ", "invalid "))
        or " unsupported " in f" {lowered} "
        or " not available" in lowered
        or " unavailable" in lowered
        or " not found" in lowered
        or " failed" in lowered
        or "failed:" in lowered
    )


def _status_is_ok(status: str) -> bool:
    lowered = _safe_str(status).lower()
    if not lowered:
        return False
    if _result_is_error(lowered):
        return False
    return not (
        "error:" in lowered
        or "timed out" in lowered
        or "timeout" in lowered
        or "page_reachable: false" in lowered
        or "reachable: false" in lowered
        or "online: false" in lowered
        or "offline" in lowered
    )


def _extract_session_id(text: str) -> str:
    match = re.search(r"session_id=([A-Za-z0-9_-]+)", text or "")
    return match.group(1) if match else ""


def _active_connect_session_path(platform: str) -> Path:
    return ENTROFLOW_HOME / "runtime" / f"{platform}_active_connect_session.json"


def _cleanup_stale_connect_artifacts(platform: str) -> None:
    runtime_dir = ENTROFLOW_HOME / "runtime"
    qr_dir = runtime_dir / "login_qr"
    if qr_dir.exists():
        for path in qr_dir.glob(f"{platform}-login-*.png"):
            try:
                path.unlink()
            except OSError:
                pass
        for path in qr_dir.glob(f"{platform}_login_*.png"):
            try:
                path.unlink()
            except OSError:
                pass
        for path in qr_dir.glob(f"{platform}-login-*.json"):
            try:
                path.unlink()
            except OSError:
                pass
        if platform == "mihome":
            for path in qr_dir.glob("mihome-login-*.png"):
                try:
                    path.unlink()
                except OSError:
                    pass
    if runtime_dir.exists():
        for path in runtime_dir.glob(f"{platform}_active_connect_session*.json"):
            try:
                path.unlink()
            except OSError:
                pass


def _write_active_connect_session(platform: str, text: str) -> None:
    session_id = _extract_session_id(text)
    if not session_id:
        return
    qr_files = re.findall(r"(?:file_path|sidecar_file_path)=([^\n]+)", text or "")
    qr_urls = re.findall(r"(?:public_url|url)=(https?://[^\s]+)", text or "")
    expires_match = re.search(r"expires_in=(\d+)", text or "")
    payload = {
        "platform": platform,
        "session_id": session_id,
        "created_at": int(time.time()),
        "expires_in": int(expires_match.group(1)) if expires_match else None,
        "qr_files": qr_files,
        "qr_urls": qr_urls,
    }
    path = _active_connect_session_path(platform)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")


def _clear_active_connect_session(platform: str, session_id: str) -> None:
    path = _active_connect_session_path(platform)
    if not path.exists():
        return
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        if session_id and payload.get("session_id") != session_id:
            return
    except Exception:
        pass
    try:
        path.unlink()
    except OSError:
        pass


def _start_connect_poller(platform: str, session_id: str, inputs: Dict[str, Any], presentation: str, timeout: int) -> None:
    if not session_id:
        return
    with _CONNECT_POLLERS_LOCK:
        existing = _CONNECT_POLLERS.get(session_id)
        if existing and existing.is_alive():
            return
        thread = threading.Thread(
            target=_connect_poll_worker,
            args=(platform, session_id, dict(inputs), presentation, timeout),
            daemon=True,
        )
        _CONNECT_POLLERS[session_id] = thread
        thread.start()


def _connect_poll_worker(platform: str, session_id: str, inputs: Dict[str, Any], presentation: str, timeout: int) -> None:
    deadline = time.time() + max(30, int(timeout or 600))
    last_result: Dict[str, Any] = {"status": "pending", "message": "Polling started."}
    while time.time() < deadline:
        try:
            text = _setup_tools_module().platform_connect_poll(
                platform,
                session_id=session_id,
                inputs=inputs,
                presentation=presentation or "url",
                timeout=timeout,
            )
            status_match = re.search(r"status=([A-Za-z0-9_-]+)", text or "")
            status = (status_match.group(1) if status_match else "").lower()
            last_result = {"status": status or "unknown", "stdout": text, "updated_at": time.time()}
            _CONNECT_POLL_RESULTS[session_id] = last_result
            if status in {"ok", "connected"}:
                _clear_active_connect_session(platform, session_id)
                _refresh_runtime_if_changed(force=True)
                return
            if status in {"expired", "failed", "error"}:
                _clear_active_connect_session(platform, session_id)
                return
        except Exception as exc:
            last_result = {"status": "error", "stderr": str(exc), "updated_at": time.time()}
            _CONNECT_POLL_RESULTS[session_id] = last_result
            if "expired" in str(exc).lower():
                _clear_active_connect_session(platform, session_id)
                return
        time.sleep(3)
    _CONNECT_POLL_RESULTS[session_id] = {**last_result, "status": "timeout", "updated_at": time.time()}
    _clear_active_connect_session(platform, session_id)


def get_login_qr_path(session_id: str) -> Path:
    safe_session_id = re.sub(r"[^A-Za-z0-9_-]", "", _safe_str(session_id))
    if not safe_session_id:
        raise ValueError("session_id is required.")
    qr_dir = (ENTROFLOW_HOME / "runtime" / "login_qr").resolve()
    matches = sorted(qr_dir.glob(f"*-{safe_session_id}.png"))
    if not matches:
        raise FileNotFoundError(f"Login QR image was not found for session_id={safe_session_id}.")
    path = matches[-1].resolve()
    if qr_dir not in path.parents:
        raise ValueError("Invalid QR image path.")
    return path


def _attach_local_qr_url(text: str) -> str:
    session_id = re.search(r"session_id=([A-Za-z0-9_-]+)", text or "")
    file_path = re.search(r"file_path=([^\n]+)", text or "")
    if not session_id or "local_qr_url=" in text:
        return text
    if file_path and not Path(file_path.group(1).strip()).expanduser().exists():
        return text
    return text.rstrip() + f"\nlocal_qr_url=/api/entroflow/qr/{session_id.group(1)}"


def execute_device_actions(device_id: str, actions: Any) -> Dict[str, Any]:
    resolved = resolve_device_id(device_id)
    if not resolved:
        raise ValueError("device_id is required.")
    record = _find_raw_device(resolved)
    if not record:
        raise ValueError(f"Device '{device_id}' is not registered in EntroFlow runtime. Use device_search first.")
    action_list = _normalize_actions(actions)
    if not action_list:
        raise ValueError("actions is required.")

    supported = set(get_action_capabilities(resolved).get("supported_actions") or [])
    results: List[EntroFlowActionResult] = []
    normalized_entries: List[tuple[str, str, Dict[str, Any]]] = []
    for entry in action_list:
        action_entry = _entry_to_dict(entry)
        if action_entry is None:
            results.append(EntroFlowActionResult("", False, "Error: each action must be an object.", {}))
            continue
        action = _safe_str(action_entry.get("action") or action_entry.get("name"))
        raw_args = _parse_args(action_entry.get("args"))
        if raw_args is None:
            results.append(EntroFlowActionResult(action, False, "Error: args must be an object.", {}))
            continue
        extra_keys = sorted(k for k in action_entry if k not in {"action", "name", "args"})
        if extra_keys:
            results.append(EntroFlowActionResult(action, False, f"Error: action parameters must be nested under args; unexpected top-level key(s): {', '.join(extra_keys)}.", raw_args))
            continue
        if not action:
            results.append(EntroFlowActionResult("", False, "Error: action is required in each item.", raw_args))
            continue
        if action == "query_status":
            results.append(EntroFlowActionResult(action, False, "Error: use device_status for query actions.", raw_args))
            continue
        runtime_action, runtime_args = _normalize_action_for_runtime(record, action, raw_args)
        if supported and runtime_action not in supported:
            results.append(EntroFlowActionResult(action, False, f"Error: action '{action}' is not supported by {resolved}.", raw_args))
            continue
        normalized_entries.append((action, runtime_action, runtime_args))

    if results:
        return {"device_id": resolved, "results": results}

    try:
        device = _create_device_instance(record)
    except Exception as exc:
        return {"device_id": resolved, "results": [EntroFlowActionResult("", False, f"Error: failed to load EntroFlow device runtime: {exc}", {})]}

    for action, runtime_action, runtime_args in normalized_entries:
        if not hasattr(device, "perform_action"):
            results.append(EntroFlowActionResult(action, False, f"Error: device '{resolved}' cannot perform actions.", runtime_args))
            continue
        try:
            raw_result = str(device.perform_action(runtime_action, **runtime_args))
        except Exception as exc:
            results.append(EntroFlowActionResult(action, False, f"Error: {exc}", runtime_args))
            continue
        results.append(EntroFlowActionResult(action, not _result_is_error(raw_result), raw_result, runtime_args))
    return {"device_id": resolved, "results": results}


def get_device_status_text(device_id: str) -> str:
    resolved = resolve_device_id(device_id)
    record = _find_raw_device(resolved)
    if not record:
        return f"Error: Device '{device_id}' was not found in EntroFlow runtime. Use device_search first."
    try:
        status = _query_device_status(record)
    except Exception as exc:
        return f"Error: failed to query EntroFlow device status: {exc}"
    return f"Device: {_device_display_name(record)} ({resolved})\n{status}"


def _load_catalog() -> List[Dict[str, Any]]:
    catalog_path = ENTROFLOW_HOME / "assets" / "catalog.json"
    if not catalog_path.exists():
        try:
            refreshed = _downloader_module().refresh_catalog()
            catalog = refreshed.get("catalog") if isinstance(refreshed, dict) else None
            platforms = catalog.get("platforms") if isinstance(catalog, dict) else []
            return [item for item in platforms if isinstance(item, dict)]
        except Exception:
            return []
    try:
        data = json.loads(catalog_path.read_text(encoding="utf-8"))
    except Exception:
        return []
    return [item for item in data.get("platforms", []) if isinstance(item, dict)]


def resolve_platform(platform: str) -> str:
    value = _safe_str(platform).lower()
    if not value:
        raise ValueError("platform is required.")
    catalog = _load_catalog()
    if not catalog:
        return value
    for entry in catalog:
        candidates = [entry.get("id"), entry.get("display_name"), *(entry.get("aliases") or [])]
        normalized = [_safe_str(item).lower() for item in candidates if _safe_str(item)]
        if value in normalized:
            return _safe_str(entry.get("id"))
    available = ", ".join(_safe_str(entry.get("id")) for entry in catalog if _safe_str(entry.get("id")))
    raise ValueError(f"Platform '{platform}' was not found. Available platforms: {available}")


def _run_entroflow_cli(args: Sequence[str], timeout: Optional[int] = None) -> Dict[str, Any]:
    command = _resolve_cli_command() + list(args)
    executable = command[0]
    if not Path(executable).exists() and shutil.which(executable) is None:
        return {"ok": False, "command": command, "stdout": "", "stderr": f"Command not found: {executable}"}
    completed = subprocess.run(
        command,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=timeout or settings.ENTROFLOW_CLI_TIMEOUT,
        check=False,
    )
    _refresh_runtime_if_changed(force=True)
    return {"ok": completed.returncode == 0, "returncode": completed.returncode, "command": command, "stdout": completed.stdout, "stderr": completed.stderr}


def _resolve_cli_command() -> List[str]:
    configured = shlex.split(settings.ENTROFLOW_CLI_COMMAND)
    if not configured:
        configured = ["entroflow"]
    executable = configured[0]
    if Path(executable).exists() or shutil.which(executable):
        return configured

    if executable == "entroflow":
        local_bin = Path.home() / ".local" / "bin" / "entroflow"
        if local_bin.exists():
            return [str(local_bin), *configured[1:]]
        embedded_cli = ENTROFLOW_HOME / "cli.py"
        embedded_python = ENTROFLOW_HOME / ".venv" / "bin" / "python"
        if embedded_cli.exists() and embedded_python.exists():
            return [str(embedded_python), str(embedded_cli), *configured[1:]]
    return configured


def run_cli_command(
    command: str,
    *,
    platform: str = "",
    query: str = "",
    supported_only: bool = False,
    did: str = "",
    model: str = "",
    version: str = "",
    name: str = "",
    location: str = "",
    remark: str = "",
    confirmed: bool = False,
    presentation: str = "",
    url: str = "",
    token: str = "",
    inputs: Optional[Dict[str, Any]] = None,
    connect_timeout: Optional[int] = None,
) -> Dict[str, Any]:
    cmd = _safe_str(command)
    if cmd == "doctor":
        return {
            "ok": True,
            "entroflow_home": str(ENTROFLOW_HOME),
            "runtime_found": (ENTROFLOW_HOME / "core" / "loader.py").exists(),
            "store_path": str(ENTROFLOW_STORE_PATH),
            "devices": len(_load_raw_devices()),
        }
    if cmd == "list_platforms":
        rows = []
        connected = set()
        try:
            connected = set(_config_module().get_connected_iot_platforms())
        except Exception:
            pass
        q = _safe_str(query).lower()
        for entry in _load_catalog():
            platform_id = _safe_str(entry.get("id"))
            display = _safe_str(entry.get("display_name")) or platform_id
            aliases = entry.get("aliases") or []
            haystack = " ".join([platform_id, display, *map(str, aliases)]).lower()
            if q and q not in haystack:
                continue
            rows.append({"id": platform_id, "display_name": display, "aliases": aliases, "connected": platform_id in connected})
        return {"ok": True, "platforms": rows, "connected_platforms": sorted(connected)}
    if cmd == "update":
        return _run_entroflow_cli(["update"])
    if cmd == "connect":
        try:
            platform_id = resolve_platform(platform)
            _cleanup_stale_connect_artifacts(platform_id)
            text = _setup_tools_module().platform_connect(
                platform_id,
                url=url,
                token=token,
                inputs=inputs or {},
                presentation=presentation or "url",
                timeout=int(connect_timeout or 600),
            )
            text = _attach_local_qr_url(text)
            session_id = _extract_session_id(text)
            if session_id:
                _write_active_connect_session(platform_id, text)
                _start_connect_poller(
                    platform_id,
                    session_id,
                    inputs or {},
                    presentation or "url",
                    int(connect_timeout or 600),
                )
                text = text.rstrip() + "\npolling=started\npolling_message=EntroFlow is polling immediately; no Enter key is required."
            _refresh_runtime_if_changed(force=True)
            return {"ok": not _result_is_error(text), "mode": "runtime_api", "stdout": text, "stderr": ""}
        except Exception as exc:
            return {"ok": False, "mode": "runtime_api", "stdout": "", "stderr": str(exc)}
    if cmd == "connect_poll":
        try:
            session_id = _safe_str((inputs or {}).get("session_id"))
            text = _setup_tools_module().platform_connect_poll(
                resolve_platform(platform),
                session_id=session_id,
                url=url,
                token=token,
                inputs=inputs or {},
                presentation=presentation or "url",
                timeout=int(connect_timeout or 600),
            )
            _refresh_runtime_if_changed(force=True)
            return {"ok": not _result_is_error(text), "mode": "runtime_api", "stdout": text, "stderr": ""}
        except Exception as exc:
            return {"ok": False, "mode": "runtime_api", "stdout": "", "stderr": str(exc)}
    if cmd == "list_devices":
        args = ["list-devices"]
        if platform:
            args.extend(["--platform", resolve_platform(platform)])
        if supported_only:
            args.append("--supported-only")
        return _run_entroflow_cli(args)
    if cmd == "setup":
        if not confirmed:
            return {"ok": False, "error": "setup requires confirmed=true after user confirmation."}
        args = ["setup", "--platform", resolve_platform(platform), "--did", _safe_str(did), "--model", _safe_str(model), "--name", _safe_str(name)]
        if version:
            args.extend(["--version", version])
        if location:
            args.extend(["--location", location])
        if remark:
            args.extend(["--remark", remark])
        return _run_entroflow_cli(args)
    return {"ok": False, "error": f"Unsupported command: {cmd}"}
