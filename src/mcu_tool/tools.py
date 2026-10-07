"""Toolchain detection and doctor report."""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

from mcu_tool.models import ToolInfo

HINTS = {
    "pio": "Install PlatformIO Core: https://docs.platformio.org/en/latest/core/installation.html",
    "cmake": "Install CMake: https://cmake.org/download/",
    "ninja": "Install Ninja: https://ninja-build.org/",
    "make": "Install make (build-essential / MSYS2)",
    "picotool": "Install picotool: https://github.com/raspberrypi/picotool",
    "PICO_SDK_PATH": "Set PICO_SDK_PATH to your Pico SDK clone: https://github.com/raspberrypi/pico-sdk",
    "idf.py": "Install ESP-IDF and run export script: https://docs.espressif.com/projects/esp-idf/",
    "IDF_PATH": "Set IDF_PATH to your ESP-IDF installation",
    "JLinkExe": "Install SEGGER J-Link: https://www.segger.com/downloads/jlink/",
    "STM32_Programmer_CLI": "Install STM32CubeProgrammer: https://www.st.com/en/development-tools/stm32cubeprog.html",
    "python": "Python 3.11+ required",
}


def _which(names: list[str]) -> str | None:
    """Resolve executables using the current process PATH (after env overrides)."""
    path_env = os.environ.get("PATH")
    for name in names:
        found = shutil.which(name, path=path_env) if path_env else shutil.which(name)
        if found:
            return found
    return None


def _version(cmd: list[str]) -> str | None:
    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=8,
            check=False,
        )
        out = (proc.stdout or proc.stderr or "").strip().splitlines()
        return out[0][:120] if out else None
    except (OSError, subprocess.TimeoutExpired):
        return None


def _pio_path() -> str | None:
    found = _which(["pio", "platformio"])
    if found:
        return found
    home = Path.home()
    candidates = [
        home / ".platformio" / "penv" / "Scripts" / "pio.exe",
        home / ".platformio" / "penv" / "bin" / "pio",
    ]
    for c in candidates:
        if c.is_file():
            return str(c)
    return None


def _idf_py_path() -> str | None:
    found = _which(["idf.py"])
    if found:
        return found
    idf_path = os.environ.get("IDF_PATH")
    if idf_path:
        candidate = Path(idf_path) / "tools" / "idf.py"
        if candidate.is_file():
            return str(candidate)
    # Common Windows installer location
    for base in (
        Path.home() / ".espressif",
        Path("C:/Espressif"),
        Path(os.environ.get("USERPROFILE", "")) / "esp" / "esp-idf",
    ):
        if not base:
            continue
        candidate = base / "tools" / "idf.py" if (base / "tools").is_dir() else base / "idf.py"
        # Also search esp-idf folder under Espressif
        if candidate.is_file():
            return str(candidate)
    return None


def _jlink_path() -> str | None:
    found = _which(["JLinkExe", "JLink.exe", "jlink"])
    if found:
        return found
    for c in (
        Path("C:/Program Files/SEGGER/JLink/JLinkExe.exe"),
        Path("C:/Program Files (x86)/SEGGER/JLink/JLinkExe.exe"),
    ):
        if c.is_file():
            return str(c)
    return None


def _stlink_path() -> str | None:
    found = _which(["STM32_Programmer_CLI", "STM32_Programmer_CLI.exe"])
    if found:
        return found
    for c in (
        Path("C:/Program Files/STMicroelectronics/STM32Cube/STM32CubeProgrammer/bin/STM32_Programmer_CLI.exe"),
        Path("C:/Program Files (x86)/STMicroelectronics/STM32Cube/STM32CubeProgrammer/bin/STM32_Programmer_CLI.exe"),
    ):
        if c.is_file():
            return str(c)
    return None


def doctor() -> list[ToolInfo]:
    """Scan toolchains from the live process environment (no result cache).

    Callers that change PATH / IDF_PATH / PICO_SDK_PATH must update ``os.environ``
    (via ``mcu_tool.envconfig``) before invoking doctor again.
    """
    from mcu_tool.envconfig import apply_to_process

    apply_to_process()
    tools: list[ToolInfo] = []

    pio = _pio_path()
    tools.append(
        ToolInfo(
            name="pio",
            status="ok" if pio else "missing",
            path=pio,
            version=_version([pio, "--version"]) if pio else None,
            hint=None if pio else HINTS["pio"],
        )
    )

    cmake = _which(["cmake"])
    tools.append(
        ToolInfo(
            name="cmake",
            status="ok" if cmake else "missing",
            path=cmake,
            version=_version([cmake, "--version"]) if cmake else None,
            hint=None if cmake else HINTS["cmake"],
        )
    )

    ninja = _which(["ninja"])
    make = _which(["make", "mingw32-make"])
    build_backend = ninja or make
    tools.append(
        ToolInfo(
            name="ninja",
            status="ok" if ninja else ("optional" if make else "missing"),
            path=ninja,
            version=_version([ninja, "--version"]) if ninja else None,
            hint=None if build_backend else HINTS["ninja"],
        )
    )
    tools.append(
        ToolInfo(
            name="make",
            status="ok" if make else "optional",
            path=make,
            version=_version([make, "--version"]) if make else None,
            hint=None if make or ninja else HINTS["make"],
        )
    )

    pico_sdk = os.environ.get("PICO_SDK_PATH")
    tools.append(
        ToolInfo(
            name="PICO_SDK_PATH",
            status="ok" if pico_sdk and Path(pico_sdk).is_dir() else "missing",
            path=pico_sdk,
            version=None,
            hint=None if pico_sdk and Path(pico_sdk).is_dir() else HINTS["PICO_SDK_PATH"],
        )
    )

    picotool = _which(["picotool"])
    tools.append(
        ToolInfo(
            name="picotool",
            status="ok" if picotool else "optional",
            path=picotool,
            version=_version([picotool, "version"]) if picotool else None,
            hint=None if picotool else HINTS["picotool"],
        )
    )

    idf_path = os.environ.get("IDF_PATH")
    tools.append(
        ToolInfo(
            name="IDF_PATH",
            status="ok" if idf_path and Path(idf_path).is_dir() else "missing",
            path=idf_path,
            version=None,
            hint=None if idf_path and Path(idf_path).is_dir() else HINTS["IDF_PATH"],
        )
    )

    idf_py = _idf_py_path()
    tools.append(
        ToolInfo(
            name="idf.py",
            status="ok" if idf_py else "missing",
            path=idf_py,
            version=None,
            hint=None if idf_py else HINTS["idf.py"],
        )
    )

    jlink = _jlink_path()
    tools.append(
        ToolInfo(
            name="JLinkExe",
            status="ok" if jlink else "optional",
            path=jlink,
            version=None,
            hint=None if jlink else HINTS["JLinkExe"],
        )
    )

    stlink = _stlink_path()
    tools.append(
        ToolInfo(
            name="STM32_Programmer_CLI",
            status="ok" if stlink else "optional",
            path=stlink,
            version=None,
            hint=None if stlink else HINTS["STM32_Programmer_CLI"],
        )
    )

    return tools


def which_tool(name: str) -> ToolInfo | None:
    name_l = name.lower().replace("-", "").replace("_", "")
    for t in doctor():
        key = t.name.lower().replace("-", "").replace("_", "")
        if key == name_l or t.name.lower() == name.lower():
            return t
    # Direct PATH lookup fallback
    path = shutil.which(name)
    if path:
        return ToolInfo(name=name, status="ok", path=path)
    return ToolInfo(name=name, status="missing", hint=HINTS.get(name))


def require_tool(name: str) -> str:
    """Return tool path or raise RuntimeError with hint."""
    info = which_tool(name)
    if not info or info.status == "missing" or not info.path:
        hint = (info.hint if info else None) or HINTS.get(name, "Install the missing toolchain.")
        raise ToolMissingError(name, hint)
    return info.path


class ToolMissingError(Exception):
    def __init__(self, name: str, hint: str) -> None:
        self.name = name
        self.hint = hint
        super().__init__(f"Tool missing: {name}. {hint}")
