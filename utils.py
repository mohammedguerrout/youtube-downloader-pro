"""
utils.py
Small, pure, side-effect-free helper functions. Kept separate from any
GUI or network code so they can be unit-tested in isolation (see
tests/test_utils.py).
"""

import os
import re

_INVALID_CHARS = re.compile(r'[\\/*?:"<>|]')
_SIZE_UNITS = ("B", "KB", "MB", "GB", "TB", "PB")


def sanitize_filename(name: str) -> str:
    """Strips characters that are invalid in Windows/macOS/Linux filenames,
    trims trailing dots/spaces, and caps the length to stay well under
    filesystem limits. Falls back to 'video' if the result is empty."""
    name = _INVALID_CHARS.sub("", name).strip().rstrip(".")
    return name[:150] or "video"


def unique_path(folder: str, name: str, ext: str) -> str:
    """Returns a filename (not a full path) guaranteed not to already
    exist in `folder`, appending ' (1)', ' (2)', ... as needed."""
    candidate = f"{name}.{ext}"
    counter = 1
    while os.path.exists(os.path.join(folder, candidate)):
        candidate = f"{name} ({counter}).{ext}"
        counter += 1
    return candidate


def format_duration(seconds: int) -> str:
    """Formats a duration in seconds as H:MM:SS, or M:SS if under an hour."""
    h, rem = divmod(int(seconds), 3600)
    m, s = divmod(rem, 60)
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"


def format_size(bytes_size: float) -> str:
    """Formats a byte count as a human-readable size (e.g. '12.34 MB').
    Handles arbitrarily large sizes up to petabytes without ever
    returning None (the original implementation silently returned None
    for sizes >= 1024 GB)."""
    size = float(bytes_size)
    for unit in _SIZE_UNITS[:-1]:
        if size < 1024.0:
            return f"{size:.2f} {unit}"
        size /= 1024.0
    return f"{size:.2f} {_SIZE_UNITS[-1]}"
