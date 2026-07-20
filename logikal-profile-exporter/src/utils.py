"""Small, dependency-free helpers.

These are deliberately kept free of pywinauto / filesystem side effects
where possible so they can be unit tested without Windows or Logikal
(see tests/test_filename_sanitizer.py).
"""

from __future__ import annotations

import re
import time
from pathlib import Path

# Characters not allowed in Windows filenames, plus a few we want to
# strip defensively even though they're technically legal (leading/
# trailing dots and spaces cause silent Windows path weirdness).
_ILLEGAL_CHARS_RE = re.compile(r'[<>:"/\\|?*\x00-\x1f]')
_RESERVED_NAMES = {
    "CON", "PRN", "AUX", "NUL",
    *(f"COM{i}" for i in range(1, 10)),
    *(f"LPT{i}" for i in range(1, 10)),
}


def sanitize_filename(article_number: str) -> str:
    """Turn an Article Number into a safe, deterministic filename stem.

    - Strips characters illegal on Windows.
    - Collapses whitespace.
    - Trims leading/trailing dots and spaces.
    - Falls back to a hash-free "ARTICLE" placeholder only if the
      cleaned result is empty (should not happen in practice, but a
      completely empty filename must never reach the filesystem).
    """
    if article_number is None:
        raise ValueError("article_number is required")

    cleaned = _ILLEGAL_CHARS_RE.sub("", str(article_number))
    cleaned = re.sub(r"\s+", "_", cleaned.strip())
    cleaned = cleaned.strip(". ")

    if not cleaned:
        cleaned = "ARTICLE"

    if cleaned.upper() in _RESERVED_NAMES:
        cleaned = f"_{cleaned}"

    return cleaned


def build_dxf_path(export_dir: Path, article_number: str) -> Path:
    """Deterministic output path for a given article inside export_dir."""
    return export_dir / f"{sanitize_filename(article_number)}.dxf"


def unique_path_with_suffix(path: Path) -> Path:
    """If `path` already exists and is NOT going to be overwritten,
    return a variant with -2, -3, ... appended before the suffix.

    Used only for the rare "two different articles produced the same
    sanitized filename" collision noted in the risk table — normal
    Skip / Overwrite logic for the *same* article does not call this.
    """
    if not path.exists():
        return path

    stem, suffix = path.stem, path.suffix
    counter = 2
    candidate = path.with_name(f"{stem}-{counter}{suffix}")
    while candidate.exists():
        counter += 1
        candidate = path.with_name(f"{stem}-{counter}{suffix}")
    return candidate


def wait_for_file_size_stable(
    path: Path,
    poll_interval: float = 0.5,
    stable_cycles: int = 3,
    timeout: float = 45.0,
) -> bool:
    """Wait until `path` exists and its size hasn't changed for
    `stable_cycles` consecutive polls. Returns False on timeout instead
    of raising, so callers can decide how to log/retry.

    This guards against reading a DXF while Logikal is still writing it
    (see risk: "file created before write completes").
    """
    deadline = time.monotonic() + timeout
    last_size = -1
    stable_count = 0

    while time.monotonic() < deadline:
        if path.exists():
            try:
                size = path.stat().st_size
            except OSError:
                size = -1

            if size == last_size and size > 0:
                stable_count += 1
                if stable_count >= stable_cycles:
                    return True
            else:
                stable_count = 0
                last_size = size
        else:
            stable_count = 0
            last_size = -1

        time.sleep(poll_interval)

    return False


def retry(times: int, exceptions: tuple = (Exception,)):
    """Small decorator-free retry helper used by dialog handling code.

    Not a decorator on purpose: automation calls usually need per-call
    recovery logic (close popup, refocus window) between attempts,
    which a generic decorator can't express cleanly. Use it as:

        for attempt in retry(3):
            try:
                ...
                break
            except SomeError:
                if attempt.is_last:
                    raise
    """

    class _Attempt:
        def __init__(self, number: int, is_last: bool):
            self.number = number
            self.is_last = is_last

    for i in range(1, times + 1):
        yield _Attempt(i, i == times)
