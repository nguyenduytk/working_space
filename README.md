# MCU Workspace Build & Flash Tool

Desktop (PySide6) + CLI tool for managing multiple MCU firmware projects (PlatformIO, Pico SDK/CMake, ESP-IDF) and flashing via UF2, J-Link, ST-Link, or vendor uploaders. It wraps toolchains already installed on your machine — it does **not** auto-install SDKs.

Windows-first; Linux CLI is supported for smoke tests and day-to-day scripting.

## Requirements

- Python 3.11+
- Optional toolchains (detected by `mcu tools doctor`):
  - [PlatformIO Core](https://docs.platformio.org/en/latest/core/installation.html) (`pio`)
  - [Pico SDK](https://github.com/raspberrypi/pico-sdk) + CMake/Ninja (`PICO_SDK_PATH`)
  - [ESP-IDF](https://docs.espressif.com/projects/esp-idf/) (`IDF_PATH`, `idf.py`)
  - [SEGGER J-Link](https://www.segger.com/downloads/jlink/) / [STM32CubeProgrammer](https://www.st.com/en/development-tools/stm32cubeprog.html)
  - [picotool](https://github.com/raspberrypi/picotool) (optional UF2 helper)

## Install

```bash
# from repo root
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -e .
```

This installs console scripts `mcu` and `mcu-gui`.

## CLI

```bash
# Workspace
mcu workspace init
mcu workspace add path/to/firmware
mcu workspace list
mcu workspace list --format json
mcu workspace remove <id|path>

# Toolchain
mcu tools doctor
mcu tools doctor --format json
mcu tools which pio

# Project
mcu project detect path/to/firmware
mcu project envs <id|path>

# Build / flash / clean
mcu build <id|path> [--env NAME] [--json-events]
mcu flash <id|path> [--env NAME] [--probe auto|uf2|jlink|stlink] [--port COM7]
mcu clean <id|path> [--env NAME]

# Serial
mcu serial list
mcu serial attach --port /dev/ttyACM0 --baud 115200

# Toolchain environment (persisted in workspace toolEnv; re-runs detect)
mcu env list
mcu env set IDF_PATH=/path/to/esp-idf
mcu env set PICO_SDK_PATH=/path/to/pico-sdk
mcu env reload
mcu env unset IDF_PATH
```

Setting SDK paths in the OS while the GUI is already running does **not** update the process. Use **Environment → Set / Re-detect** in the GUI (or `mcu env set` / `mcu env reload`) so doctor and builds see the new values.

Exit codes: `0` OK, `2` tool missing, `3` build fail, `4` flash fail, `5` workspace/project error.

Agent-friendly: use `--format json` for metadata and `--json-events` for NDJSON log streams.

## GUI

```bash
mcu-gui
# or
mcu gui
# or
python -m mcu_tool.gui
```

The window shows:

1. **Workspace sidebar** — project list, Add / Remove, Doctor
2. **Project tab** — Build / Flash / Clean, Env / Probe / Port
3. **Log pane** — streamed stdout/stderr
4. **Serial split** — connect / disconnect UART monitor

On Linux cloud VMs without a display, use the CLI (`QT_QPA_PLATFORM=offscreen` can smoke-test window construction). Desktop sessions need normal OpenGL/EGL libs (`libegl1`, `libgl1`, etc.).

## Workspace file

`mcu-workspace.json` in the current directory (or path passed to `workspace init`):

```json
{
  "version": 1,
  "name": "MCU Workspace",
  "projects": [
    {
      "id": "…",
      "path": "/path/to/project",
      "kind": "platformio",
      "displayName": "pico-blink",
      "lastEnv": "pico",
      "lastPort": "COM7",
      "notes": ""
    }
  ]
}
```

Kinds are detected from markers: `platformio.ini`, Pico CMake (`pico_sdk_import.cmake` / `pico_sdk_init`), or ESP-IDF (`sdkconfig` + `CMakeLists.txt`).

## Notes

- Missing tools are reported with install hints; flash/build fail clearly when a toolchain is absent.
- Pico flash prefers copying `.uf2` to an `RPI-RP2` / `RP2350` volume; falls back to `picotool load`.
- STM32 flash uses J-Link (`JLinkExe`) or ST-Link (`STM32_Programmer_CLI`) with ELF/HEX/BIN from `build/` (or PlatformIO `.pio/build`).
- ESP-IDF flash goes through `idf.py flash` (esptool); serial is paused during flash when connected in the GUI.
