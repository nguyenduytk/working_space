"""Project kind fingerprinting."""

from __future__ import annotations

from pathlib import Path

from mcu_tool.models import ProjectKind


def detect_kind(project_path: str | Path) -> tuple[ProjectKind, list[str]]:
    """Return detected kind and human-readable reasons.

    If multiple kinds match, returns UNKNOWN with conflict notes so the caller
    can ask the user (non-interactive → fail with message).
    """
    root = Path(project_path).resolve()
    if not root.is_dir():
        return ProjectKind.UNKNOWN, [f"Not a directory: {root}"]

    matches: list[tuple[ProjectKind, str]] = []

    pio = root / "platformio.ini"
    if pio.is_file():
        matches.append((ProjectKind.PLATFORMIO, "found platformio.ini"))

    sdkconfig = root / "sdkconfig"
    sdkconfig_defaults = root / "sdkconfig.defaults"
    cmakelists = root / "CMakeLists.txt"
    if cmakelists.is_file() and (sdkconfig.is_file() or sdkconfig_defaults.is_file()):
        text = cmakelists.read_text(encoding="utf-8", errors="ignore")
        if "idf_component_register" in text or "IDF_PATH" in text or (root / "main").is_dir():
            matches.append((ProjectKind.ESP_IDF, "ESP-IDF markers (sdkconfig + CMakeLists)"))
        elif sdkconfig.is_file() or sdkconfig_defaults.is_file():
            matches.append((ProjectKind.ESP_IDF, "sdkconfig + CMakeLists.txt"))

    pico_import = root / "pico_sdk_import.cmake"
    if cmakelists.is_file():
        text = cmakelists.read_text(encoding="utf-8", errors="ignore")
        pico_hints = (
            pico_import.is_file()
            or "pico_sdk_init" in text
            or "PICO_BOARD" in text
            or "pico_add_extra_outputs" in text
        )
        if pico_hints:
            matches.append((ProjectKind.CMAKE_PICO, "Pico SDK CMake markers"))

    # Deduplicate kinds (esp-idf and pico both need CMakeLists)
    by_kind: dict[ProjectKind, str] = {}
    for kind, reason in matches:
        by_kind[kind] = reason

    if not by_kind:
        return ProjectKind.UNKNOWN, ["No known MCU project markers found"]

    if len(by_kind) == 1:
        kind = next(iter(by_kind))
        return kind, [by_kind[kind]]

    # Prefer explicit platformio.ini over cmake heuristics when both present
    if ProjectKind.PLATFORMIO in by_kind and len(by_kind) > 1:
        # PIO projects sometimes vendor CMake — prefer PIO
        others = [k.value for k in by_kind if k != ProjectKind.PLATFORMIO]
        return ProjectKind.PLATFORMIO, [
            by_kind[ProjectKind.PLATFORMIO],
            f"also matched {', '.join(others)}; preferring platformio",
        ]

    reasons = [f"{k.value}: {r}" for k, r in by_kind.items()]
    return ProjectKind.UNKNOWN, ["Conflict — multiple kinds matched"] + reasons


def list_platformio_envs(project_path: str | Path) -> list[str]:
    ini = Path(project_path) / "platformio.ini"
    if not ini.is_file():
        return []
    envs: list[str] = []
    for line in ini.read_text(encoding="utf-8", errors="ignore").splitlines():
        line = line.strip()
        if line.startswith("[env:") and line.endswith("]"):
            envs.append(line[len("[env:") : -1].strip())
    return envs


def list_envs(project_path: str | Path, kind: ProjectKind) -> list[str]:
    if kind == ProjectKind.PLATFORMIO:
        return list_platformio_envs(project_path)
    if kind == ProjectKind.CMAKE_PICO:
        return ["default"]
    if kind == ProjectKind.ESP_IDF:
        return ["esp32", "esp32s3", "esp32c3", "esp32c6"]
    return []
