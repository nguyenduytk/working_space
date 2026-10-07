"""Subprocess runner with line streaming and process-group cancel."""

from __future__ import annotations

import os
import signal
import subprocess
import threading
from collections.abc import Callable
from typing import IO

from mcu_tool.events import EventBus

LogFn = Callable[[str, str], None]


def _stream_reader(pipe: IO[str], stream: str, on_line: LogFn, bus: EventBus | None, job_id: str | None) -> None:
    try:
        for line in iter(pipe.readline, ""):
            if not line:
                break
            text = line.rstrip("\n")
            on_line(text, stream)
            if bus:
                bus.log_line(text, stream=stream, job_id=job_id)
    finally:
        try:
            pipe.close()
        except OSError:
            pass


def run_command(
    cmd: list[str],
    *,
    cwd: str | None = None,
    env: dict[str, str] | None = None,
    bus: EventBus | None = None,
    job_id: str | None = None,
    on_line: LogFn | None = None,
    timeout: float | None = None,
) -> int:
    """Run command, stream stdout/stderr line-by-line. Returns process exit code."""
    log = on_line or (lambda _line, _stream: None)
    merged_env = os.environ.copy()
    if env:
        merged_env.update(env)

    kwargs: dict = {
        "cwd": cwd,
        "env": merged_env,
        "stdout": subprocess.PIPE,
        "stderr": subprocess.PIPE,
        "text": True,
        "bufsize": 1,
    }
    # POSIX: new process group for clean cancel
    if os.name == "posix":
        kwargs["start_new_session"] = True
    else:
        kwargs["creationflags"] = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)

    if bus:
        bus.log_line(f"$ {' '.join(cmd)}", stream="system", job_id=job_id)

    proc = subprocess.Popen(cmd, **kwargs)
    threads = [
        threading.Thread(
            target=_stream_reader,
            args=(proc.stdout, "stdout", log, bus, job_id),
            daemon=True,
        ),
        threading.Thread(
            target=_stream_reader,
            args=(proc.stderr, "stderr", log, bus, job_id),
            daemon=True,
        ),
    ]
    for t in threads:
        t.start()

    try:
        returncode = proc.wait(timeout=timeout)
    except subprocess.TimeoutExpired:
        terminate_process(proc)
        for t in threads:
            t.join(timeout=2)
        if bus:
            bus.log_line("Process timed out and was terminated", stream="system", job_id=job_id)
        return 124

    for t in threads:
        t.join(timeout=5)
    return returncode


def terminate_process(proc: subprocess.Popen) -> None:
    if proc.poll() is not None:
        return
    try:
        if os.name == "posix":
            os.killpg(proc.pid, signal.SIGTERM)
        else:
            proc.send_signal(signal.CTRL_BREAK_EVENT)  # type: ignore[attr-defined]
    except (OSError, ProcessLookupError, ValueError, AttributeError):
        try:
            proc.terminate()
        except OSError:
            pass
    try:
        proc.wait(timeout=3)
    except subprocess.TimeoutExpired:
        try:
            if os.name == "posix":
                os.killpg(proc.pid, signal.SIGKILL)
            else:
                proc.kill()
        except (OSError, ProcessLookupError):
            pass
