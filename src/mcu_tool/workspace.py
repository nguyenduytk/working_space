"""Workspace file I/O (mcu-workspace.json)."""

from __future__ import annotations

import json
from pathlib import Path

from mcu_tool.models import ExitCode, Project, Workspace

WORKSPACE_FILENAME = "mcu-workspace.json"


class WorkspaceError(Exception):
    def __init__(self, message: str, exit_code: int = ExitCode.WORKSPACE_ERROR) -> None:
        super().__init__(message)
        self.exit_code = exit_code


def default_workspace_path(base: Path | None = None) -> Path:
    root = base or Path.cwd()
    return root / WORKSPACE_FILENAME


def init_workspace(path: Path | None = None, name: str = "MCU Workspace") -> Workspace:
    ws_path = Path(path) if path else default_workspace_path()
    if ws_path.is_dir():
        ws_path = ws_path / WORKSPACE_FILENAME
    if ws_path.exists():
        return load_workspace(ws_path)
    ws = Workspace(name=name, path=str(ws_path.resolve()))
    save_workspace(ws)
    return ws


def load_workspace(path: Path | str | None = None) -> Workspace:
    ws_path = Path(path) if path else default_workspace_path()
    if ws_path.is_dir():
        ws_path = ws_path / WORKSPACE_FILENAME
    if not ws_path.exists():
        raise WorkspaceError(f"Workspace file not found: {ws_path}")
    data = json.loads(ws_path.read_text(encoding="utf-8"))
    return Workspace.from_dict(data, path=str(ws_path.resolve()))


def save_workspace(ws: Workspace) -> None:
    if not ws.path:
        raise WorkspaceError("Workspace has no path set")
    path = Path(ws.path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(ws.to_dict(), indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def find_project(ws: Workspace, id_or_path: str) -> Project:
    needle = id_or_path.strip()
    for p in ws.projects:
        if p.id == needle:
            return p
    try:
        resolved = str(Path(needle).resolve())
    except OSError:
        resolved = needle
    for p in ws.projects:
        if p.path == resolved or Path(p.path).name == needle:
            return p
    raise WorkspaceError(f"Project not found: {id_or_path}")


def add_project(ws: Workspace, project: Project) -> Project:
    for existing in ws.projects:
        if Path(existing.path).resolve() == Path(project.path).resolve():
            raise WorkspaceError(f"Project already in workspace: {project.path}")
    ws.projects.append(project)
    save_workspace(ws)
    return project


def remove_project(ws: Workspace, id_or_path: str) -> Project:
    project = find_project(ws, id_or_path)
    ws.projects = [p for p in ws.projects if p.id != project.id]
    save_workspace(ws)
    return project
