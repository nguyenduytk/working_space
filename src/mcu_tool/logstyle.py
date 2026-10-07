"""Log line classification and ANSI → role mapping for the GUI."""

from __future__ import annotations

import re
from enum import Enum


class LogRole(str, Enum):
    DEFAULT = "default"
    STDERR = "stderr"
    SYSTEM = "system"
    ERROR = "error"
    WARNING = "warning"
    INFO = "info"
    SUCCESS = "success"
    DIM = "dim"


_ANSI_RE = re.compile(r"\x1b\[[0-9;]*[mK]")
_ANSI_COLOR_RE = re.compile(r"\x1b\[([0-9;]*)m")

# Rough ANSI color → role (common toolchain output)
_ANSI_FG_ROLE = {
    "31": LogRole.ERROR,
    "91": LogRole.ERROR,
    "33": LogRole.WARNING,
    "93": LogRole.WARNING,
    "32": LogRole.SUCCESS,
    "92": LogRole.SUCCESS,
    "36": LogRole.INFO,
    "96": LogRole.INFO,
    "34": LogRole.INFO,
    "94": LogRole.INFO,
    "90": LogRole.DIM,
    "2": LogRole.DIM,
}


_ERROR_RE = re.compile(
    r"\b(error|failed|failure|fatal|exception|traceback|undefined reference|"
    r"cannot find|no such file|permission denied|tool missing)\b",
    re.I,
)
_WARN_RE = re.compile(r"\b(warning|warn|deprecated|caution)\b", re.I)
_SUCCESS_RE = re.compile(
    r"\b(success|succeeded|passed|done\.?|build complete|took\s+\d|"
    r"\[SUCCESS\]|uploaded successfully|flash.*ok)\b",
    re.I,
)
_INFO_RE = re.compile(
    r"\b(info|note:|processing|compiling|linking|building|configuring|"
    r"scanning|retrieving|looking for|LDF:|pio|cmake)\b",
    re.I,
)


def strip_ansi(text: str) -> str:
    return _ANSI_RE.sub("", text)


def role_from_ansi(text: str) -> LogRole | None:
    """If the line contains ANSI color codes, map the first meaningful FG color."""
    for match in _ANSI_COLOR_RE.finditer(text):
        codes = match.group(1).split(";") if match.group(1) else []
        for c in codes:
            if c in _ANSI_FG_ROLE:
                return _ANSI_FG_ROLE[c]
            # 38;5;n or 38;2;r;g;b — skip extended
    return None


def classify_line(line: str, stream: str = "stdout") -> tuple[str, LogRole]:
    """Return (display_text, role)."""
    ansi_role = role_from_ansi(line)
    plain = strip_ansi(line)

    if stream == "system":
        return plain, LogRole.SYSTEM
    if stream == "stderr" and not ansi_role:
        # Still allow keyword upgrade for stderr
        if _ERROR_RE.search(plain):
            return plain, LogRole.ERROR
        if _WARN_RE.search(plain):
            return plain, LogRole.WARNING
        return plain, LogRole.STDERR

    if ansi_role:
        return plain, ansi_role

    if _ERROR_RE.search(plain):
        return plain, LogRole.ERROR
    if _WARN_RE.search(plain):
        return plain, LogRole.WARNING
    if _SUCCESS_RE.search(plain):
        return plain, LogRole.SUCCESS
    if _INFO_RE.search(plain):
        return plain, LogRole.INFO
    return plain, LogRole.DEFAULT
