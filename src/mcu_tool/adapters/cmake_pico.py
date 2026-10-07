"""CMake + Pico SDK adapter."""

from __future__ import annotations

import os
import shutil
from pathlib import Path

from mcu_tool.adapters import pico_uf2
from mcu_tool.events import EventBus
from mcu_tool.models import ExitCode, JobResult, ProbeType, Project, ProjectKind
from mcu_tool.process import run_command
from mcu_tool.tools import ToolMissingError, require_tool


class CMakePicoAdapter:
    kind = ProjectKind.CMAKE_PICO

    def list_envs(self, project: Project) -> list[str]:
        return ["default"]

    def _build_dir(self, project: Project, env: str | None) -> Path:
        if env and env not in ("default", ""):
            return Path(project.path) / f"build-{env}"
        return Path(project.path) / "build"

    def build(
        self,
        project: Project,
        *,
        env: str | None,
        bus: EventBus,
        job_id: str,
    ) -> JobResult:
        try:
            cmake = require_tool("cmake")
        except ToolMissingError as e:
            bus.log_line(str(e), stream="stderr", job_id=job_id)
            return JobResult(False, ExitCode.TOOL_MISSING, str(e))

        sdk = os.environ.get("PICO_SDK_PATH")
        if not sdk or not Path(sdk).is_dir():
            msg = (
                "PICO_SDK_PATH is not set or invalid. "
                "https://github.com/raspberrypi/pico-sdk"
            )
            bus.log_line(msg, stream="stderr", job_id=job_id)
            return JobResult(False, ExitCode.TOOL_MISSING, msg)

        build_dir = self._build_dir(project, env)
        build_dir.mkdir(parents=True, exist_ok=True)

        generator = "Ninja" if shutil.which("ninja") else "Unix Makefiles"
        if os.name == "nt" and not shutil.which("ninja"):
            # Prefer Ninja on Windows when available; else MinGW Makefiles if make present
            if shutil.which("mingw32-make"):
                generator = "MinGW Makefiles"
            else:
                generator = "Ninja"  # still try; cmake will error clearly

        configure = [
            cmake,
            "-S",
            project.path,
            "-B",
            str(build_dir),
            f"-G{generator}",
            f"-DPICO_SDK_PATH={sdk}",
        ]
        if env and env not in ("default", ""):
            configure.append(f"-DPICO_BOARD={env}")

        code = run_command(configure, cwd=project.path, bus=bus, job_id=job_id)
        if code != 0:
            return JobResult(False, ExitCode.BUILD_FAIL, f"cmake configure exited {code}")

        build_cmd = [cmake, "--build", str(build_dir)]
        code = run_command(build_cmd, cwd=project.path, bus=bus, job_id=job_id)
        if code != 0:
            return JobResult(False, ExitCode.BUILD_FAIL, f"cmake build exited {code}")

        uf2 = pico_uf2.find_uf2_artifact(project.path, str(build_dir))
        return JobResult(
            True,
            ExitCode.OK,
            "Build succeeded",
            artifact=str(uf2) if uf2 else None,
        )

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
        del port  # UF2 path does not need COM
        build_dir = self._build_dir(project, env)
        uf2 = pico_uf2.find_uf2_artifact(project.path, str(build_dir))
        if not uf2:
            bus.log_line("No .uf2 found — building first...", stream="system", job_id=job_id)
            built = self.build(project, env=env, bus=bus, job_id=job_id)
            if not built.ok:
                return built
            uf2 = Path(built.artifact) if built.artifact else pico_uf2.find_uf2_artifact(
                project.path, str(build_dir)
            )
        if not uf2:
            return JobResult(False, ExitCode.FLASH_FAIL, "No .uf2 artifact after build")

        if probe in (ProbeType.AUTO, ProbeType.UF2):
            result = pico_uf2.flash_uf2(uf2, bus=bus, job_id=job_id)
            if result.ok:
                return result
            # Fallback to picotool load
            bus.log_line("UF2 volume flash failed — trying picotool load...", stream="system", job_id=job_id)
            return pico_uf2.flash_picotool_load(uf2, bus=bus, job_id=job_id)

        # Explicit non-UF2: try picotool
        return pico_uf2.flash_picotool_load(uf2, bus=bus, job_id=job_id)

    def clean(
        self,
        project: Project,
        *,
        env: str | None,
        bus: EventBus,
        job_id: str,
    ) -> JobResult:
        build_dir = self._build_dir(project, env)
        if build_dir.is_dir():
            bus.log_line(f"Removing {build_dir}", stream="system", job_id=job_id)
            shutil.rmtree(build_dir, ignore_errors=True)
        return JobResult(True, ExitCode.OK, "Clean succeeded")
