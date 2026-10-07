"""Core service: workspace ops + job orchestration (shared by CLI and GUI)."""

from __future__ import annotations

import uuid
from collections.abc import Callable
from pathlib import Path

from mcu_tool.adapters.base import get_adapter
from mcu_tool.adapters import stm_flash
from mcu_tool.detect import detect_kind, list_envs
from mcu_tool.events import EventBus
from mcu_tool.models import (
    ExitCode,
    JobResult,
    ProbeType,
    Project,
    ProjectKind,
    Workspace,
)
from mcu_tool import envconfig
from mcu_tool import workspace as ws_io
from mcu_tool.tools import doctor, which_tool


class CoreService:
    def __init__(self, bus: EventBus | None = None) -> None:
        self.bus = bus or EventBus()
        self.workspace: Workspace | None = None
        self._active_jobs: dict[str, str] = {}  # project_id -> job_id
        self._serial_paused_for_flash = False

    def _sync_tool_env_from_workspace(self) -> None:
        if self.workspace is not None:
            envconfig.load_overrides(self.workspace.toolEnv, apply=True)

    def _persist_tool_env(self) -> None:
        if self.workspace is None:
            return
        self.workspace.toolEnv = envconfig.get_overrides()
        ws_io.save_workspace(self.workspace)

    # --- workspace ---

    def init_workspace(self, path: str | None = None, name: str = "MCU Workspace") -> Workspace:
        self.workspace = ws_io.init_workspace(Path(path) if path else None, name=name)
        self._sync_tool_env_from_workspace()
        return self.workspace

    def load_workspace(self, path: str | None = None) -> Workspace:
        self.workspace = ws_io.load_workspace(Path(path) if path else None)
        self._sync_tool_env_from_workspace()
        return self.workspace

    def ensure_workspace(self, path: str | None = None) -> Workspace:
        if self.workspace:
            return self.workspace
        try:
            return self.load_workspace(path)
        except ws_io.WorkspaceError:
            return self.init_workspace(path)

    def add_project(
        self,
        project_path: str,
        *,
        kind: ProjectKind | None = None,
        yes: bool = False,
    ) -> Project:
        ws = self.ensure_workspace()
        root = Path(project_path).resolve()
        if not root.is_dir():
            raise ws_io.WorkspaceError(f"Not a directory: {root}")

        detected, reasons = detect_kind(root)
        if kind is None:
            if detected == ProjectKind.UNKNOWN:
                conflict = any("Conflict" in r for r in reasons)
                msg = "; ".join(reasons)
                if conflict and not yes:
                    raise ws_io.WorkspaceError(
                        f"Could not uniquely detect project kind at {root}: {msg}. "
                        "Pass an explicit kind or --yes to skip."
                    )
                if detected == ProjectKind.UNKNOWN and not conflict:
                    raise ws_io.WorkspaceError(f"Unknown project kind: {msg}")
            kind = detected

        project = Project.create(str(root), kind)
        ws_io.add_project(ws, project)
        return project

    def remove_project(self, id_or_path: str) -> Project:
        ws = self.ensure_workspace()
        return ws_io.remove_project(ws, id_or_path)

    def list_projects(self) -> list[Project]:
        ws = self.ensure_workspace()
        return list(ws.projects)

    def get_project(self, id_or_path: str) -> Project:
        ws = self.ensure_workspace()
        return ws_io.find_project(ws, id_or_path)

    def save_project_prefs(
        self,
        project: Project,
        *,
        env: str | None = None,
        port: str | None = None,
        probe: str | None = None,
    ) -> None:
        if env is not None:
            project.lastEnv = env
        if port is not None:
            project.lastPort = port
        if probe is not None:
            project.lastProbe = probe
        if self.workspace:
            ws_io.save_workspace(self.workspace)

    # --- tools ---

    def tools_doctor(self):
        envconfig.apply_to_process()
        return doctor()

    def tools_which(self, name: str):
        envconfig.apply_to_process()
        return which_tool(name)

    # --- tool environment ---

    def env_list(self) -> list[tuple[str, str, str]]:
        self.ensure_workspace()
        return envconfig.list_relevant()

    def env_set(self, key: str, value: str) -> None:
        self.ensure_workspace()
        envconfig.set_override(key, value, apply=True)
        self._persist_tool_env()

    def env_unset(self, key: str) -> None:
        self.ensure_workspace()
        envconfig.unset_override(key, apply=True)
        self._persist_tool_env()

    def env_reload(self) -> list:
        """Re-apply workspace toolEnv to the process and re-run doctor."""
        self.ensure_workspace()
        self._sync_tool_env_from_workspace()
        return self.tools_doctor()

    # --- project inspect ---

    def detect_project(self, path: str) -> tuple[ProjectKind, list[str]]:
        return detect_kind(path)

    def project_envs(self, id_or_path: str) -> list[str]:
        # Allow path not yet in workspace
        try:
            project = self.get_project(id_or_path)
            return list_envs(project.path, project.kind)
        except ws_io.WorkspaceError:
            kind, _ = detect_kind(id_or_path)
            return list_envs(id_or_path, kind)

    # --- jobs ---

    def _new_job(self, action: str, project: Project | None) -> str:
        job_id = str(uuid.uuid4())[:8]
        pid = project.id if project else None
        if project:
            self._active_jobs[project.id] = job_id
        self.bus.job_started(job_id, action, project_id=pid)
        return job_id

    def _finish(self, job_id: str, result: JobResult, project: Project | None) -> JobResult:
        if project and self._active_jobs.get(project.id) == job_id:
            self._active_jobs.pop(project.id, None)
        self.bus.job_finished(
            job_id,
            ok=result.ok,
            exit_code=result.exit_code,
            message=result.message,
            artifact=result.artifact,
        )
        return result

    def build(self, id_or_path: str, *, env: str | None = None) -> JobResult:
        project = self._resolve_runnable(id_or_path)
        job_id = self._new_job("build", project)
        try:
            adapter = get_adapter(project.kind)
            use_env = env or project.lastEnv
            result = adapter.build(project, env=use_env, bus=self.bus, job_id=job_id)
            if use_env:
                self.save_project_prefs(project, env=use_env)
            return self._finish(job_id, result, project)
        except Exception as e:  # noqa: BLE001
            result = JobResult(False, ExitCode.BUILD_FAIL, str(e))
            self.bus.log_line(str(e), stream="stderr", job_id=job_id)
            return self._finish(job_id, result, project)

    def flash(
        self,
        id_or_path: str,
        *,
        env: str | None = None,
        probe: ProbeType = ProbeType.AUTO,
        port: str | None = None,
        firmware: str | None = None,
        pause_serial: Callable[[], None] | None = None,
        resume_serial: Callable[[], None] | None = None,
    ) -> JobResult:
        project = self._resolve_runnable(id_or_path)
        job_id = self._new_job("flash", project)
        use_env = env or project.lastEnv
        use_port = port or project.lastPort
        use_probe = probe
        if project.lastProbe and probe == ProbeType.AUTO:
            try:
                use_probe = ProbeType(project.lastProbe)
            except ValueError:
                pass

        if pause_serial:
            try:
                pause_serial()
                self._serial_paused_for_flash = True
            except Exception:  # noqa: BLE001
                pass

        try:
            # STM flash path: when user asks stm probes on non-ESP/Pico, or kind unknown with firmware
            if use_probe in (ProbeType.JLINK, ProbeType.STLINK) or (
                project.kind == ProjectKind.UNKNOWN
            ):
                result = stm_flash.flash_stm(
                    project.path,
                    probe=use_probe if use_probe != ProbeType.UF2 else ProbeType.AUTO,
                    bus=self.bus,
                    job_id=job_id,
                    firmware=firmware,
                )
            elif project.kind == ProjectKind.PLATFORMIO and use_probe in (
                ProbeType.JLINK,
                ProbeType.STLINK,
            ):
                # Allow STM via PIO build artifact + external probe
                result = stm_flash.flash_stm(
                    project.path,
                    probe=use_probe,
                    bus=self.bus,
                    job_id=job_id,
                    firmware=firmware,
                )
            else:
                adapter = get_adapter(project.kind)
                result = adapter.flash(
                    project,
                    env=use_env,
                    probe=use_probe,
                    bus=self.bus,
                    job_id=job_id,
                    port=use_port,
                )

            self.save_project_prefs(
                project,
                env=use_env,
                port=use_port,
                probe=use_probe.value if use_probe != ProbeType.AUTO else project.lastProbe,
            )
            return self._finish(job_id, result, project)
        except Exception as e:  # noqa: BLE001
            result = JobResult(False, ExitCode.FLASH_FAIL, str(e))
            self.bus.log_line(str(e), stream="stderr", job_id=job_id)
            return self._finish(job_id, result, project)
        finally:
            if self._serial_paused_for_flash and resume_serial:
                try:
                    resume_serial()
                except Exception:  # noqa: BLE001
                    pass
                self._serial_paused_for_flash = False

    def clean(self, id_or_path: str, *, env: str | None = None) -> JobResult:
        project = self._resolve_runnable(id_or_path)
        job_id = self._new_job("clean", project)
        try:
            adapter = get_adapter(project.kind)
            use_env = env or project.lastEnv
            result = adapter.clean(project, env=use_env, bus=self.bus, job_id=job_id)
            return self._finish(job_id, result, project)
        except Exception as e:  # noqa: BLE001
            result = JobResult(False, ExitCode.BUILD_FAIL, str(e))
            self.bus.log_line(str(e), stream="stderr", job_id=job_id)
            return self._finish(job_id, result, project)

    def _resolve_runnable(self, id_or_path: str) -> Project:
        """Resolve project from workspace, or synthesize from path detection."""
        try:
            return self.get_project(id_or_path)
        except ws_io.WorkspaceError:
            root = Path(id_or_path)
            if root.is_dir():
                kind, _ = detect_kind(root)
                return Project.create(str(root.resolve()), kind)
            raise
