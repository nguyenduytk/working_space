"""Unit tests for detect + workspace (no hardware)."""

from __future__ import annotations

import json
from pathlib import Path

from mcu_tool.detect import detect_kind, list_platformio_envs
from mcu_tool.models import ProjectKind
from mcu_tool.service import CoreService
from mcu_tool.tools import doctor


def test_detect_platformio(tmp_path: Path) -> None:
    (tmp_path / "platformio.ini").write_text("[env:pico]\nplatform = raspberrypi\n")
    kind, reasons = detect_kind(tmp_path)
    assert kind == ProjectKind.PLATFORMIO
    assert reasons


def test_detect_cmake_pico(tmp_path: Path) -> None:
    (tmp_path / "pico_sdk_import.cmake").write_text("# pico\n")
    (tmp_path / "CMakeLists.txt").write_text("cmake_minimum_required(VERSION 3.13)\npico_sdk_init()\n")
    kind, _ = detect_kind(tmp_path)
    assert kind == ProjectKind.CMAKE_PICO


def test_detect_esp_idf(tmp_path: Path) -> None:
    (tmp_path / "sdkconfig").write_text("CONFIG_IDF_TARGET=\"esp32\"\n")
    (tmp_path / "CMakeLists.txt").write_text("cmake_minimum_required(VERSION 3.16)\ninclude($ENV{IDF_PATH}/tools/cmake/project.cmake)\n")
    (tmp_path / "main").mkdir()
    kind, _ = detect_kind(tmp_path)
    assert kind == ProjectKind.ESP_IDF


def test_list_pio_envs(tmp_path: Path) -> None:
    (tmp_path / "platformio.ini").write_text("[env:pico]\n\n[env:stm32]\n")
    assert list_platformio_envs(tmp_path) == ["pico", "stm32"]


def test_workspace_roundtrip(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    svc = CoreService()
    ws = svc.init_workspace(name="Lab")
    assert Path(ws.path).is_file()

    proj = tmp_path / "fw"
    proj.mkdir()
    (proj / "platformio.ini").write_text("[env:pico]\n")
    added = svc.add_project(str(proj))
    assert added.kind == ProjectKind.PLATFORMIO
    listed = svc.list_projects()
    assert len(listed) == 1
    data = json.loads(Path(ws.path).read_text())
    assert data["name"] == "Lab"
    assert data["projects"][0]["kind"] == "platformio"


def test_doctor_returns_tools() -> None:
    tools = doctor()
    names = {t.name for t in tools}
    assert "pio" in names
    assert "cmake" in names
    assert "idf.py" in names
