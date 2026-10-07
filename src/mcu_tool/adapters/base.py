"""Adapter protocol and registry."""

from __future__ import annotations

from typing import Protocol

from mcu_tool.events import EventBus
from mcu_tool.models import JobResult, ProbeType, Project, ProjectKind


class Adapter(Protocol):
    kind: ProjectKind

    def list_envs(self, project: Project) -> list[str]: ...

    def build(
        self,
        project: Project,
        *,
        env: str | None,
        bus: EventBus,
        job_id: str,
    ) -> JobResult: ...

    def flash(
        self,
        project: Project,
        *,
        env: str | None,
        probe: ProbeType,
        bus: EventBus,
        job_id: str,
        port: str | None = None,
    ) -> JobResult: ...

    def clean(
        self,
        project: Project,
        *,
        env: str | None,
        bus: EventBus,
        job_id: str,
    ) -> JobResult: ...


def get_adapter(kind: ProjectKind) -> Adapter:
    if kind == ProjectKind.PLATFORMIO:
        from mcu_tool.adapters.platformio import PlatformIOAdapter

        return PlatformIOAdapter()
    if kind == ProjectKind.CMAKE_PICO:
        from mcu_tool.adapters.cmake_pico import CMakePicoAdapter

        return CMakePicoAdapter()
    if kind == ProjectKind.ESP_IDF:
        from mcu_tool.adapters.esp_idf import EspIdfAdapter

        return EspIdfAdapter()
    raise ValueError(f"No adapter for kind: {kind.value}")
