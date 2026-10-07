"""CLI entry: `mcu`."""

from __future__ import annotations

import json
import sys
from enum import Enum
from pathlib import Path
from typing import Optional

import typer
from rich.console import Console
from rich.table import Table

from mcu_tool import __version__
from mcu_tool.adapters import serial_mon
from mcu_tool.events import EventBus
from mcu_tool.models import ExitCode, ProbeType, ProjectKind
from mcu_tool.service import CoreService
from mcu_tool.workspace import WorkspaceError

app = typer.Typer(
    name="mcu",
    help="MCU Workspace Build & Flash Tool",
    no_args_is_help=True,
    add_completion=False,
)
workspace_app = typer.Typer(help="Workspace management", no_args_is_help=True)
tools_app = typer.Typer(help="Toolchain detection", no_args_is_help=True)
project_app = typer.Typer(help="Project inspect", no_args_is_help=True)
serial_app = typer.Typer(help="Serial monitor", no_args_is_help=True)

app.add_typer(workspace_app, name="workspace")
app.add_typer(tools_app, name="tools")
app.add_typer(project_app, name="project")
app.add_typer(serial_app, name="serial")

console = Console(stderr=False)
err_console = Console(stderr=True)


class Format(str, Enum):
    text = "text"
    json = "json"


def _service(json_events: bool = False) -> tuple[CoreService, EventBus]:
    bus = EventBus()
    if json_events:

        def _handler(ev) -> None:  # noqa: ANN001
            print(ev.to_json(), flush=True)

        bus.subscribe(_handler)
    else:

        def _handler(ev) -> None:  # noqa: ANN001
            if ev.type == "log.line":
                stream = ev.payload.get("stream", "stdout")
                line = ev.payload.get("line", "")
                if stream == "stderr":
                    err_console.print(line, style="red")
                elif stream == "system":
                    console.print(f"[dim]{line}[/dim]")
                else:
                    console.print(line)

        bus.subscribe(_handler)
    return CoreService(bus), bus


def _die(msg: str, code: int) -> None:
    err_console.print(f"[red]{msg}[/red]")
    raise typer.Exit(code)


@app.callback()
def main_callback(
    version: bool = typer.Option(False, "--version", help="Show version and exit"),
) -> None:
    if version:
        console.print(__version__)
        raise typer.Exit(0)


# --- workspace ---


@workspace_app.command("init")
def workspace_init(
    path: Optional[Path] = typer.Argument(None, help="Directory or mcu-workspace.json path"),
    name: str = typer.Option("MCU Workspace", "--name"),
    format: Format = typer.Option(Format.text, "--format"),
) -> None:
    svc, _ = _service()
    try:
        ws = svc.init_workspace(str(path) if path else None, name=name)
    except WorkspaceError as e:
        _die(str(e), e.exit_code)
    if format == Format.json:
        print(json.dumps(ws.to_dict(), indent=2))
    else:
        console.print(f"Workspace ready: [bold]{ws.path}[/bold] ({ws.name})")


@workspace_app.command("add")
def workspace_add(
    project_path: Path = typer.Argument(..., help="Firmware project directory"),
    kind: Optional[str] = typer.Option(None, "--kind", help="platformio|cmake-pico|esp-idf"),
    yes: bool = typer.Option(False, "--yes", "-y"),
    format: Format = typer.Option(Format.text, "--format"),
    workspace: Optional[Path] = typer.Option(None, "--workspace", "-w"),
) -> None:
    svc, _ = _service()
    try:
        svc.ensure_workspace(str(workspace) if workspace else None)
        pk = ProjectKind(kind) if kind else None
        project = svc.add_project(str(project_path), kind=pk, yes=yes)
    except (WorkspaceError, ValueError) as e:
        code = getattr(e, "exit_code", ExitCode.WORKSPACE_ERROR)
        _die(str(e), code)
    if format == Format.json:
        print(json.dumps(project.to_dict(), indent=2))
    else:
        console.print(
            f"Added [bold]{project.displayName}[/bold] "
            f"({project.kind.value}) id={project.id}"
        )


@workspace_app.command("remove")
def workspace_remove(
    id_or_path: str = typer.Argument(...),
    format: Format = typer.Option(Format.text, "--format"),
    workspace: Optional[Path] = typer.Option(None, "--workspace", "-w"),
) -> None:
    svc, _ = _service()
    try:
        svc.ensure_workspace(str(workspace) if workspace else None)
        project = svc.remove_project(id_or_path)
    except WorkspaceError as e:
        _die(str(e), e.exit_code)
    if format == Format.json:
        print(json.dumps(project.to_dict(), indent=2))
    else:
        console.print(f"Removed {project.displayName} ({project.id})")


@workspace_app.command("list")
def workspace_list(
    format: Format = typer.Option(Format.text, "--format"),
    workspace: Optional[Path] = typer.Option(None, "--workspace", "-w"),
) -> None:
    svc, _ = _service()
    try:
        svc.ensure_workspace(str(workspace) if workspace else None)
        projects = svc.list_projects()
    except WorkspaceError as e:
        _die(str(e), e.exit_code)
    if format == Format.json:
        print(json.dumps([p.to_dict() for p in projects], indent=2))
        return
    if not projects:
        console.print("No projects in workspace.")
        return
    table = Table(title="Workspace projects")
    table.add_column("ID")
    table.add_column("Name")
    table.add_column("Kind")
    table.add_column("Path")
    for p in projects:
        table.add_row(p.id[:8], p.displayName, p.kind.value, p.path)
    console.print(table)


# --- tools ---


@tools_app.command("doctor")
def tools_doctor(format: Format = typer.Option(Format.text, "--format")) -> None:
    svc, _ = _service()
    tools = svc.tools_doctor()
    if format == Format.json:
        print(json.dumps([t.to_dict() for t in tools], indent=2))
        return
    table = Table(title="Toolchain doctor")
    table.add_column("Tool")
    table.add_column("Status")
    table.add_column("Path / Version")
    table.add_column("Hint")
    for t in tools:
        style = {"ok": "green", "missing": "red", "optional": "yellow"}.get(t.status, "")
        loc = t.path or ""
        if t.version:
            loc = f"{loc}\n{t.version}" if loc else t.version
        table.add_row(t.name, f"[{style}]{t.status}[/{style}]", loc, t.hint or "")
    console.print(table)


@tools_app.command("which")
def tools_which(
    name: str = typer.Argument(...),
    format: Format = typer.Option(Format.text, "--format"),
) -> None:
    svc, _ = _service()
    info = svc.tools_which(name)
    if not info:
        _die(f"Unknown tool: {name}", ExitCode.TOOL_MISSING)
    if format == Format.json:
        print(json.dumps(info.to_dict(), indent=2))
        return
    console.print(f"{info.name}: {info.status} {info.path or ''}")
    if info.hint:
        console.print(info.hint)
    if info.status == "missing":
        raise typer.Exit(ExitCode.TOOL_MISSING)


# --- project ---


@project_app.command("detect")
def project_detect(
    path: Path = typer.Argument(...),
    format: Format = typer.Option(Format.text, "--format"),
) -> None:
    svc, _ = _service()
    kind, reasons = svc.detect_project(str(path))
    payload = {"kind": kind.value, "reasons": reasons, "path": str(path.resolve())}
    if format == Format.json:
        print(json.dumps(payload, indent=2))
    else:
        console.print(f"Kind: [bold]{kind.value}[/bold]")
        for r in reasons:
            console.print(f"  - {r}")


@project_app.command("envs")
def project_envs(
    id_or_path: str = typer.Argument(...),
    format: Format = typer.Option(Format.text, "--format"),
    workspace: Optional[Path] = typer.Option(None, "--workspace", "-w"),
) -> None:
    svc, _ = _service()
    try:
        if workspace:
            svc.ensure_workspace(str(workspace))
        envs = svc.project_envs(id_or_path)
    except WorkspaceError as e:
        _die(str(e), e.exit_code)
    if format == Format.json:
        print(json.dumps({"envs": envs}, indent=2))
    else:
        for e in envs:
            console.print(e)


# --- build / flash / clean ---


@app.command("build")
def build_cmd(
    id_or_path: str = typer.Argument(...),
    env: Optional[str] = typer.Option(None, "--env", "-e"),
    json_events: bool = typer.Option(False, "--json-events"),
    workspace: Optional[Path] = typer.Option(None, "--workspace", "-w"),
) -> None:
    svc, _ = _service(json_events=json_events)
    try:
        if workspace:
            svc.ensure_workspace(str(workspace))
        result = svc.build(id_or_path, env=env)
    except WorkspaceError as e:
        _die(str(e), e.exit_code)
    if not json_events:
        style = "green" if result.ok else "red"
        console.print(f"[{style}]{result.message}[/{style}]")
    raise typer.Exit(result.exit_code if not result.ok else 0)


@app.command("flash")
def flash_cmd(
    id_or_path: str = typer.Argument(...),
    env: Optional[str] = typer.Option(None, "--env", "-e"),
    probe: str = typer.Option("auto", "--probe", help="jlink|stlink|uf2|auto"),
    port: Optional[str] = typer.Option(None, "--port", "-p"),
    firmware: Optional[str] = typer.Option(None, "--firmware", help="ELF/HEX/BIN for STM flash"),
    json_events: bool = typer.Option(False, "--json-events"),
    workspace: Optional[Path] = typer.Option(None, "--workspace", "-w"),
) -> None:
    try:
        probe_t = ProbeType(probe.lower())
    except ValueError:
        _die(f"Invalid probe: {probe}", ExitCode.WORKSPACE_ERROR)
    svc, _ = _service(json_events=json_events)
    try:
        if workspace:
            svc.ensure_workspace(str(workspace))
        result = svc.flash(
            id_or_path,
            env=env,
            probe=probe_t,
            port=port,
            firmware=firmware,
        )
    except WorkspaceError as e:
        _die(str(e), e.exit_code)
    if not json_events:
        style = "green" if result.ok else "red"
        console.print(f"[{style}]{result.message}[/{style}]")
    raise typer.Exit(result.exit_code if not result.ok else 0)


@app.command("clean")
def clean_cmd(
    id_or_path: str = typer.Argument(...),
    env: Optional[str] = typer.Option(None, "--env", "-e"),
    json_events: bool = typer.Option(False, "--json-events"),
    workspace: Optional[Path] = typer.Option(None, "--workspace", "-w"),
) -> None:
    svc, _ = _service(json_events=json_events)
    try:
        if workspace:
            svc.ensure_workspace(str(workspace))
        result = svc.clean(id_or_path, env=env)
    except WorkspaceError as e:
        _die(str(e), e.exit_code)
    if not json_events:
        style = "green" if result.ok else "red"
        console.print(f"[{style}]{result.message}[/{style}]")
    raise typer.Exit(result.exit_code if not result.ok else 0)


# --- serial ---


@serial_app.command("list")
def serial_list(format: Format = typer.Option(Format.text, "--format")) -> None:
    ports = serial_mon.list_serial_ports()
    if format == Format.json:
        print(json.dumps([p.to_dict() for p in ports], indent=2))
        return
    if not ports:
        console.print("No serial ports found.")
        return
    table = Table(title="Serial ports")
    table.add_column("Device")
    table.add_column("Description")
    table.add_column("HWID")
    for p in ports:
        table.add_row(p.device, p.description, p.hwid)
    console.print(table)


@serial_app.command("attach")
def serial_attach(
    port: str = typer.Option(..., "--port", "-p"),
    baud: int = typer.Option(115200, "--baud", "-b"),
    format: Format = typer.Option(Format.text, "--format"),
) -> None:
    code = serial_mon.attach_cli(port, baud, json_events=(format == Format.json))
    raise typer.Exit(code)


@app.command("gui")
def gui_cmd() -> None:
    """Launch the PySide6 desktop GUI."""
    from mcu_tool.gui.app import main as gui_main

    gui_main()


def main() -> None:
    app()


if __name__ == "__main__":
    main()
