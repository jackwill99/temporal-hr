import json
from pathlib import Path
from typing import Dict, List

from .config import DATA_DIR, FAILED_JSON_PATH, TEMP_JSON_PATH


def _read_json(path: Path) -> List[Dict]:
    if path.exists():
        try:
            with open(path, "r", encoding="utf-8") as handle:
                return json.load(handle)
        except json.JSONDecodeError:
            return []
    return []


def _write_json(path: Path, entries: List[Dict]) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(entries, handle, indent=2)


def append_application_record(record: Dict) -> None:
    entries = _read_json(TEMP_JSON_PATH)
    entries.append(record)
    _write_json(TEMP_JSON_PATH, entries)


def append_failed_record(record: Dict) -> None:
    entries = _read_json(FAILED_JSON_PATH)
    entries.append(record)
    _write_json(FAILED_JSON_PATH, entries)


def get_unnotified_failed() -> List[Dict]:
    return [row for row in _read_json(FAILED_JSON_PATH) if not row.get("notified_at")]


def mark_failed_notified(failure_ids: List[str]) -> None:
    entries = _read_json(FAILED_JSON_PATH)
    updated: List[Dict] = []
    for row in entries:
        if row.get("id") in failure_ids and not row.get("notified_at"):
            row["notified_at"] = row.get("notified_at") or None
            if row["notified_at"] is None:
                from datetime import datetime

                row["notified_at"] = datetime.utcnow().isoformat() + "Z"
        updated.append(row)
    _write_json(FAILED_JSON_PATH, updated)
