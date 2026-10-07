"""Session / workspace tool environment overlays.

Root cause of stale toolchain detect: doctor and adapters read ``os.environ`` /
``shutil.which`` from the long-lived process. Setting IDF_PATH / PATH / etc. in
the shell or OS UI does not update an already-running GUI/CLI process, and there
was no in-app way to apply overrides then re-run doctor.
"""

from __future__ import annotations

import os
import threading
from typing import Any

# Keys commonly needed for MCU toolchains — shown in GUI shortcuts.
COMMON_KEYS = (
    "PATH",
    "PICO_SDK_PATH",
    "IDF_PATH",
    "PLATFORMIO_CORE_DIR",
    "PICO_BOARD",
    "ESP_IDF_VERSION",
)

_lock = threading.RLock()
# Overrides applied on top of process env (and persisted on the workspace).
_overrides: dict[str, str] = {}


def get_overrides() -> dict[str, str]:
    with _lock:
        return dict(_overrides)


def set_override(key: str, value: str, *, apply: bool = True) -> None:
    key = key.strip()
    if not key:
        raise ValueError("Environment variable name is empty")
    with _lock:
        _overrides[key] = value
        if apply:
            os.environ[key] = value


def unset_override(key: str, *, apply: bool = True) -> None:
    key = key.strip()
    with _lock:
        _overrides.pop(key, None)
        if apply:
            # Do not delete from os.environ if it came from the parent process
            # unless we had overridden it — restore is best-effort: just remove
            # our override; leave os.environ as last applied value unless value
            # was only ours. Simplest: delete key from os.environ when unsetting
            # an override so doctor re-reads absence (user can reload shell env
            # by restarting). Documented behavior.
            os.environ.pop(key, None)


def clear_overrides(*, apply: bool = True) -> None:
    with _lock:
        keys = list(_overrides.keys())
        _overrides.clear()
        if apply:
            for k in keys:
                os.environ.pop(k, None)


def load_overrides(data: dict[str, Any] | None, *, apply: bool = True) -> None:
    """Replace session overrides from a persisted mapping."""
    with _lock:
        _overrides.clear()
        if data:
            for k, v in data.items():
                if k and v is not None:
                    _overrides[str(k)] = str(v)
        if apply:
            apply_to_process()


def apply_to_process() -> None:
    """Write current overrides into ``os.environ`` (PATH-aware which/doctor)."""
    with _lock:
        for k, v in _overrides.items():
            os.environ[k] = v


def effective_environ(extra: dict[str, str] | None = None) -> dict[str, str]:
    """Copy of process env with overrides (and optional per-call extras)."""
    env = os.environ.copy()
    with _lock:
        env.update(_overrides)
    if extra:
        env.update(extra)
    return env


def list_relevant() -> list[tuple[str, str, str]]:
    """Return (key, value, source) for overrides + common keys present in env."""
    rows: list[tuple[str, str, str]] = []
    seen: set[str] = set()
    with _lock:
        for k, v in sorted(_overrides.items()):
            rows.append((k, v, "override"))
            seen.add(k)
    for k in COMMON_KEYS:
        if k in seen:
            continue
        if k in os.environ:
            rows.append((k, os.environ[k], "process"))
            seen.add(k)
    return rows
