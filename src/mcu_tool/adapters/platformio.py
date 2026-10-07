"""PlatformIO adapter."""

from __future__ import annotations

from mcu_tool.detect import list_platformio_envs
from mcu_tool.events import EventBus
from mcu_tool.models import ExitCode, JobResult, ProbeType, Project, ProjectKind
from mcu_tool.process import run_command
from mcu_tool.tools import ToolMissingError, require_tool


class PlatformIOAdapter:
    kind = ProjectKind.PLATFORMIO

    def list_envs(self, project: Project) -> list[str]:
        return list_platformio_envs(project.path)

    def _pio(self) -> str:
        return require_tool("pio")

    def build(
        self,
        project: Project,
        *,
        env: str | None,
        bus: EventBus,
        job_id: str,
    ) -> JobResult:
        try:
            pio = self._pio()
        except ToolMissingError as e:
            bus.log_line(str(e), stream="stderr", job_id=job_id)
            return JobResult(False, ExitCode.TOOL_MISSING, str(e))

        cmd = [pio, "run"]
        if env:
            cmd.extend(["-e", env])
        code = run_command(cmd, cwd=project.path, bus=bus, job_id=job_id)
        if code != 0:
            return JobResult(False, ExitCode.BUILD_FAIL, f"pio run exited {code}")
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
        try:
            pio = self._pio()
        except ToolMissingError as e:
            bus.log_line(str(e), stream="stderr", job_id=job_id)
            return JobResult(False, ExitCode.TOOL_MISSING, str(e))

        cmd = [pio, "run", "-t", "upload"]
        if env:
            cmd.extend(["-e", env])
        if port:
            cmd.extend(["--upload-port", port])
        # probe is informational for PIO — board upload_protocol is in ini
        if probe != ProbeType.AUTO:
            bus.log_line(
                f"Note: probe={probe.value} — PlatformIO uses upload_protocol from platformio.ini",
                stream="system",
                job_id=job_id,
            )
        code = run_command(cmd, cwd=project.path, bus=bus, job_id=job_id)
        if code != 0:
            return JobResult(False, ExitCode.FLASH_FAIL, f"pio upload exited {code}")
        return JobResult(True, ExitCode.OK, "Flash succeeded")

    def clean(
        self,
        project: Project,
        *,
        env: str | None,
        bus: EventBus,
        job_id: str,
    ) -> JobResult:
        try:
            pio = self._pio()
        except ToolMissingError as e:
            bus.log_line(str(e), stream="stderr", job_id=job_id)
            return JobResult(False, ExitCode.TOOL_MISSING, str(e))

        cmd = [pio, "run", "-t", "clean"]
        if env:
            cmd.extend(["-e", env])
        code = run_command(cmd, cwd=project.path, bus=bus, job_id=job_id)
        if code != 0:
            return JobResult(False, ExitCode.BUILD_FAIL, f"pio clean exited {code}")
        return JobResult(True, ExitCode.OK, "Clean succeeded")
