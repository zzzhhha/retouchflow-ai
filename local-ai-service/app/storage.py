from __future__ import annotations

import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

BEIJING_TZ = timezone(timedelta(hours=8), "Asia/Shanghai")


def run_root() -> Path:
    env_root = os.getenv("AI_RETOUCH_RUN_ROOT")
    if env_root:
        return Path(env_root)
    return Path(__file__).resolve().parents[1] / "runs"


def batch_dir(batch_id: str) -> Path:
    safe_id = safe_batch_id(batch_id)
    path = run_root() / safe_id
    path.mkdir(parents=True, exist_ok=True)
    return path


def safe_batch_id(batch_id: str) -> str:
    safe_id = "".join(ch for ch in batch_id if ch.isalnum() or ch in {"-", "_"})
    if safe_id == "":
        raise ValueError("Invalid batch id")
    return safe_id


def event_log_path() -> Path:
    path = run_root() / "events.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def save_json(batch_id: str, name: str, payload: Any) -> Path:
    path = batch_dir(batch_id) / f"{name}.json"
    envelope = {
        "saved_at": _now_beijing(),
        "payload": payload,
    }
    path.write_text(json.dumps(envelope, ensure_ascii=False, indent=2), encoding="utf-8")
    append_event("save_json", batch_id=batch_id, file=path.name)
    return path


def append_event(event: str, **payload: Any) -> None:
    record = {
        "time": _now_beijing(),
        "event": event,
        **payload,
    }
    with event_log_path().open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, ensure_ascii=False) + "\n")


def list_batches() -> list[dict[str, Any]]:
    root = run_root()
    if not root.exists():
        return []

    batches: list[dict[str, Any]] = []
    for path in root.iterdir():
        if not path.is_dir():
            continue
        files = sorted(file for file in path.glob("*.json") if file.is_file())
        updated_at = max((file.stat().st_mtime for file in files), default=path.stat().st_mtime)
        photo_count = _photo_count_from_analyze(path / "analyze.json")
        batches.append(
            {
                "batch_id": path.name,
                "updated_at": _timestamp_to_beijing(updated_at),
                "file_count": photo_count if photo_count > 0 else len(files),
                "photo_count": photo_count,
                "data_file_count": len(files),
                "files": [file.name for file in files],
            }
        )

    return sorted(batches, key=lambda item: item["updated_at"], reverse=True)


def _photo_count_from_analyze(path: Path) -> int:
    if not path.exists():
        return 0
    try:
        envelope = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return 0
    payload = envelope.get("payload") if isinstance(envelope, dict) else {}
    photos = payload.get("photos") if isinstance(payload, dict) else []
    return len(photos) if isinstance(photos, list) else 0


def batch_files(batch_id: str) -> list[dict[str, Any]]:
    path = run_root() / safe_batch_id(batch_id)
    if not path.exists():
        return []
    files: list[dict[str, Any]] = []
    for file in sorted(path.glob("*.json")):
        stat = file.stat()
        files.append(
            {
                "name": file.name,
                "size": stat.st_size,
                "updated_at": _timestamp_to_beijing(stat.st_mtime),
            }
        )
    return files


def read_batch_json(batch_id: str, file_name: str) -> dict[str, Any]:
    safe_id = safe_batch_id(batch_id)
    safe_name = Path(file_name).name
    if safe_name != file_name or not safe_name.endswith(".json"):
        raise ValueError("Invalid batch file name")

    path = run_root() / safe_id / safe_name
    root = run_root().resolve()
    resolved = path.resolve()
    if root not in resolved.parents:
        raise ValueError("Invalid batch file path")
    if not resolved.exists():
        raise FileNotFoundError(file_name)
    return json.loads(resolved.read_text(encoding="utf-8"))


def recent_events(limit: int = 100) -> list[dict[str, Any]]:
    path = event_log_path()
    if not path.exists():
        return []
    lines = path.read_text(encoding="utf-8").splitlines()[-limit:]
    events: list[dict[str, Any]] = []
    for line in lines:
        try:
            event = json.loads(line)
            if "time" in event:
                event["time"] = _iso_to_beijing(str(event["time"]))
            events.append(event)
        except json.JSONDecodeError:
            continue
    return list(reversed(events))


def _now_beijing() -> str:
    return datetime.now(BEIJING_TZ).isoformat(timespec="seconds")


def _timestamp_to_beijing(timestamp: float) -> str:
    return datetime.fromtimestamp(timestamp, BEIJING_TZ).isoformat(timespec="seconds")


def _iso_to_beijing(value: str) -> str:
    try:
        normalized = value.replace("Z", "+00:00")
        parsed = datetime.fromisoformat(normalized)
    except ValueError:
        return value
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(BEIJING_TZ).isoformat(timespec="seconds")
