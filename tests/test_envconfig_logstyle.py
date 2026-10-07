"""Tests for env overrides + log classification."""

from __future__ import annotations

import os
from pathlib import Path

from mcu_tool import envconfig
from mcu_tool.logstyle import LogRole, classify_line, strip_ansi
from mcu_tool.service import CoreService
from mcu_tool.tools import doctor


def test_strip_and_classify_ansi() -> None:
    text, role = classify_line("\x1b[31merror: boom\x1b[0m", "stdout")
    assert "error" in text
    assert "\x1b" not in text
    assert role == LogRole.ERROR


def test_classify_keywords() -> None:
    assert classify_line("WARNING: deprecated", "stdout")[1] == LogRole.WARNING
    assert classify_line("SUCCESS Took 1.2 seconds", "stdout")[1] == LogRole.SUCCESS
    assert classify_line("Compiling .pio/build/x/main.o", "stdout")[1] == LogRole.INFO
    assert classify_line("hello", "stderr")[1] == LogRole.STDERR
    assert strip_ansi("\x1b[32mok\x1b[0m") == "ok"


def test_env_override_updates_doctor(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    envconfig.clear_overrides(apply=True)
    # Ensure a fake SDK path is missing then present
    fake = tmp_path / "pico-sdk"
    assert not (os.environ.get("PICO_SDK_PATH") and Path(os.environ["PICO_SDK_PATH"]).is_dir())

    svc = CoreService()
    svc.init_workspace(name="EnvTest")
    before = {t.name: t for t in svc.tools_doctor()}
    assert before["PICO_SDK_PATH"].status == "missing"

    fake.mkdir()
    svc.env_set("PICO_SDK_PATH", str(fake))
    after = {t.name: t for t in svc.tools_doctor()}
    assert after["PICO_SDK_PATH"].status == "ok"
    assert after["PICO_SDK_PATH"].path == str(fake)

    # Persisted on workspace
    assert svc.workspace is not None
    assert svc.workspace.toolEnv.get("PICO_SDK_PATH") == str(fake)

    # Reload still sees it
    tools = svc.env_reload()
    assert {t.name: t for t in tools}["PICO_SDK_PATH"].status == "ok"

    svc.env_unset("PICO_SDK_PATH")
    again = {t.name: t for t in doctor()}
    assert again["PICO_SDK_PATH"].status == "missing"
