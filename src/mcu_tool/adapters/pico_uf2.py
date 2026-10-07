"""Pico UF2 flash: locate RPI-RP2 volume and copy .uf2."""

from __future__ import annotations

import shutil
import time
from pathlib import Path

from mcu_tool.events import EventBus
from mcu_tool.models import ExitCode, JobResult
from mcu_tool.process import run_command
from mcu_tool.tools import which_tool

UF2_LABELS = ("RPI-RP2", "RP2350")


def find_uf2_artifact(project_path: str, build_dir: str | None = None) -> Path | None:
    root = Path(project_path)
    search_roots = []
    if build_dir:
        search_roots.append(Path(build_dir))
    search_roots.extend(
        [
            root / "build",
            root / ".pio" / "build",
        ]
    )
    # Also scan env dirs under .pio/build
    pio_build = root / ".pio" / "build"
    if pio_build.is_dir():
        search_roots.extend(sorted(pio_build.iterdir()))

    candidates: list[Path] = []
    for base in search_roots:
        if not base.is_dir():
            continue
        candidates.extend(base.rglob("*.uf2"))
    if not candidates:
        return None
    candidates.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    return candidates[0]


def _is_pico_volume(path: Path) -> bool:
    name = path.name.upper()
    if any(label in name for label in UF2_LABELS):
        return True
    return (path / "INFO_UF2.TXT").is_file()


def list_boot_volumes() -> list[Path]:
    """Find Pico BOOTSEL mass-storage mounts (Windows drive letters / Linux media)."""
    found: list[Path] = []

    def _scan(dir_path: Path, depth: int = 0) -> None:
        if depth > 2 or not dir_path.is_dir():
            return
        try:
            children = list(dir_path.iterdir())
        except PermissionError:
            return
        for child in children:
            if not child.is_dir():
                continue
            if _is_pico_volume(child):
                found.append(child)
            elif depth < 2:
                _scan(child, depth + 1)

    for base in (Path("/media"), Path("/run/media"), Path("/mnt"), Path("/Volumes")):
        _scan(base, 0)

    # Windows: scan drive letters for INFO_UF2.TXT
    import string

    for letter in string.ascii_uppercase:
        drive = Path(f"{letter}:/")
        try:
            exists = drive.exists()
        except OSError:
            exists = False
        if exists and _is_pico_volume(drive):
            found.append(drive)

    uniq: list[Path] = []
    seen: set[str] = set()
    for p in found:
        try:
            key = str(p.resolve())
        except OSError:
            key = str(p)
        if key not in seen:
            seen.add(key)
            uniq.append(p)
    return uniq


def try_reset_bootsel(bus: EventBus, job_id: str) -> None:
    """Best-effort reset into BOOTSEL via picotool."""
    info = which_tool("picotool")
    if not info or not info.path or info.status == "missing":
        bus.log_line(
            "picotool not found — put the board into BOOTSEL manually (hold BOOTSEL while plugging USB)",
            stream="system",
            job_id=job_id,
        )
        return
    bus.log_line("Attempting picotool reboot -f -u (BOOTSEL)...", stream="system", job_id=job_id)
    code = run_command(
        [info.path, "reboot", "-f", "-u"],
        bus=bus,
        job_id=job_id,
        timeout=10,
    )
    if code != 0:
        bus.log_line(
            "picotool reboot failed — enter BOOTSEL manually if needed",
            stream="system",
            job_id=job_id,
        )


def flash_uf2(
    uf2_path: Path,
    *,
    bus: EventBus,
    job_id: str,
    timeout_s: float = 45.0,
    try_reset: bool = True,
) -> JobResult:
    if not uf2_path.is_file():
        msg = f"UF2 not found: {uf2_path}"
        bus.log_line(msg, stream="stderr", job_id=job_id)
        return JobResult(False, ExitCode.FLASH_FAIL, msg)

    bus.log_line(f"UF2 artifact: {uf2_path}", stream="system", job_id=job_id)

    volumes = list_boot_volumes()
    if not volumes and try_reset:
        try_reset_bootsel(bus, job_id)
        deadline = time.time() + timeout_s
        bus.log_line(
            f"Waiting up to {int(timeout_s)}s for RPI-RP2 / RP2350 volume...",
            stream="system",
            job_id=job_id,
        )
        while time.time() < deadline:
            volumes = list_boot_volumes()
            if volumes:
                break
            time.sleep(0.5)

    if not volumes:
        msg = (
            "No Pico BOOTSEL volume found (expected label RPI-RP2 / RP2350). "
            "Hold BOOTSEL, plug USB, then retry flash."
        )
        bus.log_line(msg, stream="stderr", job_id=job_id)
        return JobResult(False, ExitCode.FLASH_FAIL, msg)

    dest_dir = volumes[0]
    dest = dest_dir / uf2_path.name
    bus.log_line(f"Copying to {dest} ...", stream="system", job_id=job_id)
    try:
        shutil.copy2(uf2_path, dest)
    except OSError as e:
        msg = f"Failed to copy UF2: {e}"
        bus.log_line(msg, stream="stderr", job_id=job_id)
        return JobResult(False, ExitCode.FLASH_FAIL, msg)

    bus.log_line("UF2 copied — board should reboot shortly", stream="system", job_id=job_id)
    return JobResult(True, ExitCode.OK, f"Flashed {uf2_path.name} via UF2", artifact=str(uf2_path))


def flash_picotool_load(
    artifact: Path,
    *,
    bus: EventBus,
    job_id: str,
) -> JobResult:
    info = which_tool("picotool")
    if not info or not info.path:
        return JobResult(
            False,
            ExitCode.TOOL_MISSING,
            "picotool missing for load fallback",
        )
    cmd = [info.path, "load", str(artifact), "-f"]
    code = run_command(cmd, bus=bus, job_id=job_id, timeout=60)
    if code != 0:
        return JobResult(False, ExitCode.FLASH_FAIL, f"picotool load exited {code}")
    return JobResult(True, ExitCode.OK, "Flashed via picotool load", artifact=str(artifact))
