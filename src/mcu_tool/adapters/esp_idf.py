"""ESP-IDF adapter (idf.py wrapper)."""

from __future__ import annotations

import os
import sys
from pathlib import Path

from mcu_tool.events import EventBus
from mcu_tool.models import ExitCode, JobResult, ProbeType, Project, ProjectKind
from mcu_tool.process import run_command
from mcu_tool.tools import ToolMissingError, which_tool


class EspIdfAdapter:
    kind = ProjectKind.ESP_IDF

    def list_envs(self, project: Project) -> list[str]:
        return ["esp32", "esp32s3", "esp32c3", "esp32c6"]

    def _resolve_idf(self, project: Project) -> tuple[str, dict[str, str] | None]:
        env_extra: dict[str, str] = {}
        idf_path = project.idfPath or os.environ.get("IDF_PATH")
        if idf_path:
            env_extra["IDF_PATH"] = idf_path

        info = which_tool("idf.py")
        if info and info.path and info.status == "ok":
            return info.path, env_extra or None

        if idf_path:
            candidate = Path(idf_path) / "tools" / "idf.py"
            if candidate.is_file():
                return str(candidate), env_extra or None

        raise ToolMissingError(
            "idf.py",
            "Install ESP-IDF and run its export script: https://docs.espressif.com/projects/esp-idf/",
        )

    def _idf_cmd(self, idf_py: str, *args: str) -> list[str]:
        # idf.py is a Python script — invoke via current interpreter when needed
        if idf_py.endswith(".py"):
            return [sys.executable, idf_py, *args]
        return [idf_py, *args]

    def build(
        self,
        project: Project,
        *,
        env: str | None,
        bus: EventBus,
        job_id: str,
    ) -> JobResult:
        try:
            idf_py, extra = self._resolve_idf(project)
        except ToolMissingError as e:
            bus.log_line(str(e), stream="stderr", job_id=job_id)
            return JobResult(False, ExitCode.TOOL_MISSING, str(e))

        if env and env not in ("default", ""):
            set_cmd = self._idf_cmd(idf_py, "set-target", env)
            code = run_command(set_cmd, cwd=project.path, env=extra, bus=bus, job_id=job_id)
            if code != 0:
                return JobResult(False, ExitCode.BUILD_FAIL, f"idf.py set-target exited {code}")

        cmd = self._idf_cmd(idf_py, "build")
        code = run_command(cmd, cwd=project.path, env=extra, bus=bus, job_id=job_id)
        if code != 0:
            return JobResult(False, ExitCode.BUILD_FAIL, f"idf.py build exited {code}")
        return JobResult(True, ExitCode.OK, "Build succeeded")

    def flash(
        self,
        project: Project,
        *,
        env: str | None,
        probe: ProbeType,
        bus: EventBus,
        job_id: str,
        port: str | None = None,
    ) -> JobResult:
        del probe  # ESP uses esptool via idf.py
        try:
            idf_py, extra = self._resolve_idf(project)
        except ToolMissingError as e:
            bus.log_line(str(e), stream="stderr", job_id=job_id)
            return JobResult(False, ExitCode.TOOL_MISSING, str(e))

        args = ["flash"]
        if port:
            args.extend(["-p", port])
        cmd = self._idf_cmd(idf_py, *args)
        code = run_command(cmd, cwd=project.path, env=extra, bus=bus, job_id=job_id)
        if code != 0:
            return JobResult(False, ExitCode.FLASH_FAIL, f"idf.py flash exited {code}")
        return JobResult(True, ExitCode.OK, "Flash succeeded")

    def clean(
        self,
        project: Project,
        *,
        env: str | None,
        bus: EventBus,
        job_id: str,
    ) -> JobResult:
        del env
        try:
            idf_py, extra = self._resolve_idf(project)
        except ToolMissingError as e:
            bus.log_line(str(e), stream="stderr", job_id=job_id)
            return JobResult(False, ExitCode.TOOL_MISSING, str(e))

        cmd = self._idf_cmd(idf_py, "fullclean")
        code = run_command(cmd, cwd=project.path, env=extra, bus=bus, job_id=job_id)
        if code != 0:
            return JobResult(False, ExitCode.BUILD_FAIL, f"idf.py fullclean exited {code}")
        return JobResult(True, ExitCode.OK, "Clean succeeded")
