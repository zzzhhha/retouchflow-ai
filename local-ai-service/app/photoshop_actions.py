from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any


DEFAULT_ACTION_CONFIG = Path(__file__).resolve().parents[1] / "config" / "photoshop_actions.json"


def action_config_path() -> Path:
    env_path = os.getenv("AI_RETOUCH_PHOTOSHOP_ACTIONS", "").strip()
    if env_path:
        return Path(env_path)
    return DEFAULT_ACTION_CONFIG


def load_photoshop_action_config(path: str | Path | None = None) -> dict[str, Any]:
    config_path = Path(path) if path else action_config_path()
    if not config_path.exists():
        return {"enabled": False, "actions": {}, "path": str(config_path)}
    try:
        payload = json.loads(config_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"enabled": False, "actions": {}, "path": str(config_path), "error": "invalid_json"}
    if not isinstance(payload, dict):
        return {"enabled": False, "actions": {}, "path": str(config_path), "error": "invalid_config"}
    actions = payload.get("actions") if isinstance(payload.get("actions"), dict) else {}
    return {
        "enabled": payload.get("enabled", True) is not False,
        "actions": actions,
        "path": str(config_path),
    }


def apply_photoshop_action_config(operations: list[dict[str, Any]]) -> list[dict[str, Any]]:
    config = load_photoshop_action_config()
    if not config.get("enabled"):
        return [dict(operation) for operation in operations]
    actions = config.get("actions") if isinstance(config.get("actions"), dict) else {}
    result: list[dict[str, Any]] = []
    for operation in operations:
        item = dict(operation)
        action = _action_for_operation(item, actions)
        if action:
            item["photoshop_action"] = action
        result.append(item)
    return result


def photoshop_action_status() -> dict[str, Any]:
    config = load_photoshop_action_config()
    actions = config.get("actions") if isinstance(config.get("actions"), dict) else {}
    return {
        "enabled": bool(config.get("enabled")),
        "path": config.get("path", ""),
        "configured_operation_count": len(actions),
        "operations": sorted(str(key) for key in actions.keys()),
        "error": config.get("error", ""),
    }


def _action_for_operation(operation: dict[str, Any], actions: dict[str, Any]) -> dict[str, Any]:
    keys = [
        str(operation.get("type") or "").strip(),
        str(operation.get("id") or "").strip(),
    ]
    for key in keys:
        raw = actions.get(key)
        if not isinstance(raw, dict):
            continue
        action_set = str(raw.get("set") or raw.get("action_set") or "").strip()
        action_name = str(raw.get("action") or raw.get("name") or "").strip()
        if not action_set or not action_name:
            continue
        return {
            "set": action_set,
            "action": action_name,
            "required": raw.get("required", False) is True,
        }
    return {}
