"""STM32 flash via J-Link or ST-Link (CubeProgrammer)."""

from __future__ import annotations

import tempfile
from pathlib import Path

from mcu_tool.events import EventBus
from mcu_tool.models import ExitCode, JobResult, ProbeType
from mcu_tool.process import run_command
from mcu_tool.tools import ToolMissingError, which_tool


def find_firmware(project_path: str, explicit: str | None = None) -> Path | None:
    if explicit:
        p = Path(explicit)
        return p if p.is_file() else None

    root = Path(project_path)
    patterns = ("*.elf", "*.hex", "*.bin")
    candidates: list[Path] = []
    search_dirs = [
        root / "build",
        root / "Build",
        root / "cmake-build-debug",
        root / "cmake-build-release",
        root / ".pio" / "build",
    ]
    for d in search_dirs:
        if not d.is_dir():
            continue
        for pat in patterns:
            candidates.extend(d.rglob(pat))
    # Prefer .elf then .hex
    for ext in (".elf", ".hex", ".bin"):
        matched = [c for c in candidates if c.suffix.lower() == ext]
        if matched:
            matched.sort(key=lambda p: p.stat().st_mtime, reverse=True)
            return matched[0]
    return None


def detect_probe() -> ProbeType:
    jlink = which_tool("JLinkExe")
    stlink = which_tool("STM32_Programmer_CLI")
    j_ok = jlink and jlink.path and jlink.status != "missing"
    s_ok = stlink and stlink.path and stlink.status != "missing"
    if j_ok and not s_ok:
        return ProbeType.JLINK
    if s_ok and not j_ok:
        return ProbeType.STLINK
    if j_ok:
        return ProbeType.JLINK  # default preference when both present
    return ProbeType.AUTO


def flash_jlink(
    firmware: Path,
    *,
    bus: EventBus,
    job_id: str,
    device: str | None = None,
) -> JobResult:
    info = which_tool("JLinkExe")
    if not info or not info.path:
        raise ToolMissingError(
            "JLinkExe",
            "Install SEGGER J-Link: https://www.segger.com/downloads/jlink/",
        )

    # Minimal commander script: load file, reset, go, quit
    load_cmd = f'LoadFile "{firmware}"'
    script_lines = [
        "si SWD",
        "speed 4000",
        f"device {device}" if device else "device STM32F103C8",
        "r",
        "h",
        load_cmd,
        "r",
        "g",
        "q",
    ]
    with tempfile.NamedTemporaryFile(
        mode="w",
        suffix=".jlink",
        delete=False,
        encoding="utf-8",
    ) as tf:
        tf.write("\n".join(script_lines) + "\n")
        script_path = tf.name

    bus.log_line(f"J-Link script: {script_path}", stream="system", job_id=job_id)
    cmd = [info.path, "-CommanderScript", script_path]
    # Windows often uses JLink.exe with -CommandFile
    if info.path.lower().endswith("jlink.exe"):
        cmd = [info.path, "-CommandFile", script_path]

    code = run_command(cmd, bus=bus, job_id=job_id, timeout=120)
    try:
        Path(script_path).unlink(missing_ok=True)
    except OSError:
        pass

    if code != 0:
        return JobResult(False, ExitCode.FLASH_FAIL, f"JLinkExe exited {code}")
    return JobResult(True, ExitCode.OK, "Flashed via J-Link", artifact=str(firmware))


def flash_stlink(
    firmware: Path,
    *,
    bus: EventBus,
    job_id: str,
) -> JobResult:
    info = which_tool("STM32_Programmer_CLI")
    if not info or not info.path:
        raise ToolMissingError(
            "STM32_Programmer_CLI",
            "Install STM32CubeProgrammer: https://www.st.com/en/development-tools/stm32cubeprog.html",
        )

    # Connect via SWD, download, run
    cmd = [
        info.path,
        "-c",
        "port=SWD",
        "mode=UR",
        "-w",
        str(firmware),
        "0x08000000" if firmware.suffix.lower() == ".bin" else "",
        "-v",
        "-rst",
        "-run",
    ]
    # Remove empty args (for elf/hex address not needed)
    cmd = [c for c in cmd if c]

    code = run_command(cmd, bus=bus, job_id=job_id, timeout=120)
    if code != 0:
        return JobResult(False, ExitCode.FLASH_FAIL, f"STM32_Programmer_CLI exited {code}")
    return JobResult(True, ExitCode.OK, "Flashed via ST-Link", artifact=str(firmware))


def flash_stm(
    project_path: str,
    *,
    probe: ProbeType,
    bus: EventBus,
    job_id: str,
    firmware: str | None = None,
    device: str | None = None,
) -> JobResult:
    fw = find_firmware(project_path, firmware)
    if not fw:
        msg = (
            "No ELF/HEX/BIN found under build/. "
            "Build the STM32 firmware first, or pass an explicit firmware path."
        )
        bus.log_line(msg, stream="stderr", job_id=job_id)
        return JobResult(False, ExitCode.FLASH_FAIL, msg)

    bus.log_line(f"Firmware: {fw}", stream="system", job_id=job_id)

    chosen = probe
    if chosen == ProbeType.AUTO:
        chosen = detect_probe()
        if chosen == ProbeType.AUTO:
            msg = (
                "No J-Link or STM32_Programmer_CLI found. "
                "Install a probe toolchain and retry with --probe jlink|stlink."
            )
            bus.log_line(msg, stream="stderr", job_id=job_id)
            return JobResult(False, ExitCode.TOOL_MISSING, msg)
        bus.log_line(f"Auto-selected probe: {chosen.value}", stream="system", job_id=job_id)

    try:
        if chosen == ProbeType.JLINK:
            return flash_jlink(fw, bus=bus, job_id=job_id, device=device)
        if chosen == ProbeType.STLINK:
            return flash_stlink(fw, bus=bus, job_id=job_id)
        msg = f"Unsupported STM probe: {chosen.value}"
        bus.log_line(msg, stream="stderr", job_id=job_id)
        return JobResult(False, ExitCode.FLASH_FAIL, msg)
    except ToolMissingError as e:
        bus.log_line(str(e), stream="stderr", job_id=job_id)
        return JobResult(False, ExitCode.TOOL_MISSING, str(e))
