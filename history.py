"""
history.py
Persisted, in-app download history (separate from the technical log
file). Stored as a simple JSON list, capped at MAX_ENTRIES so the file
never grows unbounded.
"""

import json
import time
from pathlib import Path
from typing import Optional

HISTORY_FILE = Path.home() / ".yt_downloader_history.json"
MAX_ENTRIES = 200


def load_history() -> list[dict]:
    try:
        return json.loads(HISTORY_FILE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []


def _save(entries: list[dict]) -> None:
    try:
        HISTORY_FILE.write_text(json.dumps(entries, ensure_ascii=False, indent=2), encoding="utf-8")
    except OSError:
        pass  # history is a convenience feature; never crash the app over it


def add_entry(title: str, path: str, kind: str, size: int) -> None:
    """kind: 'video' | 'audio' | 'mp3' | 'subtitles'"""
    entries = load_history()
    entries.insert(0, {
        "title": title,
        "path": path,
        "kind": kind,
        "size": size,
        "timestamp": time.time(),
        "date": time.strftime("%Y-%m-%d %H:%M"),
    })
    _save(entries[:MAX_ENTRIES])


def remove_entry(index: int) -> None:
    entries = load_history()
    if 0 <= index < len(entries):
        entries.pop(index)
        _save(entries)


def clear_history() -> None:
    _save([])
