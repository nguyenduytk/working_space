"""Shared data models for workspace and projects."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any
from uuid import uuid4


class ProjectKind(str, Enum):
    PLATFORMIO = "platformio"
    CMAKE_PICO = "cmake-pico"
    ESP_IDF = "esp-idf"
    UNKNOWN = "unknown"


class ExitCode:
    OK = 0
    TOOL_MISSING = 2
    BUILD_FAIL = 3
    FLASH_FAIL = 4
    WORKSPACE_ERROR = 5


class ProbeType(str, Enum):
    AUTO = "auto"
    JLINK = "jlink"
    STLINK = "stlink"
    UF2 = "uf2"


@dataclass
class Project:
    id: str
    path: str
    kind: ProjectKind
    displayName: str
    lastEnv: str | None = None
    lastPort: str | None = None
    notes: str = ""
    lastProbe: str | None = None
    idfPath: str | None = None

    @staticmethod
    def create(
        path: str,
        kind: ProjectKind,
        display_name: str | None = None,
    ) -> Project:
        from pathlib import Path

        p = Path(path).resolve()
        return Project(
            id=str(uuid4()),
            path=str(p),
            kind=kind,
            displayName=display_name or p.name,
        )

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["kind"] = self.kind.value
        return d

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Project:
        kind_raw = data.get("kind", "unknown")
        try:
            kind = ProjectKind(kind_raw)
        except ValueError:
            kind = ProjectKind.UNKNOWN
        return cls(
            id=data["id"],
            path=data["path"],
            kind=kind,
            displayName=data.get("displayName") or data.get("display_name") or "project",
            lastEnv=data.get("lastEnv") or data.get("last_env"),
            lastPort=data.get("lastPort") or data.get("last_port"),
            notes=data.get("notes") or "",
            lastProbe=data.get("lastProbe") or data.get("last_probe"),
            idfPath=data.get("idfPath") or data.get("idf_path"),
        )


@dataclass
class Workspace:
    version: int = 1
    name: str = "MCU Workspace"
    projects: list[Project] = field(default_factory=list)
    path: str | None = None  # path to mcu-workspace.json

    def to_dict(self) -> dict[str, Any]:
        return {
            "version": self.version,
            "name": self.name,
            "projects": [p.to_dict() for p in self.projects],
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any], path: str | None = None) -> Workspace:
        projects = [Project.from_dict(p) for p in data.get("projects", [])]
        return cls(
            version=int(data.get("version", 1)),
            name=data.get("name") or "MCU Workspace",
            projects=projects,
            path=path,
        )


@dataclass
class ToolInfo:
    name: str
    status: str  # ok | missing | optional
    path: str | None = None
    version: str | None = None
    hint: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class JobResult:
    ok: bool
    exit_code: int
    message: str = ""
    artifact: str | None = None
