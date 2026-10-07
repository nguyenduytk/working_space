"""Serial monitor using pyserial."""

from __future__ import annotations

import sys
import threading
import time
from dataclasses import dataclass
from typing import Callable

from mcu_tool.events import EventBus

try:
    import serial
    from serial.tools import list_ports
except ImportError:  # pragma: no cover
    serial = None  # type: ignore[assignment]
    list_ports = None  # type: ignore[assignment]


@dataclass
class PortInfo:
    device: str
    description: str
    hwid: str
    vid: int | None = None
    pid: int | None = None

    def to_dict(self) -> dict:
        return {
            "device": self.device,
            "description": self.description,
            "hwid": self.hwid,
            "vid": self.vid,
            "pid": self.pid,
        }


def list_serial_ports() -> list[PortInfo]:
    if list_ports is None:
        return []
    result: list[PortInfo] = []
    for p in list_ports.comports():
        result.append(
            PortInfo(
                device=p.device,
                description=p.description or "",
                hwid=p.hwid or "",
                vid=p.vid,
                pid=p.pid,
            )
        )
    return result


class SerialMonitor:
    """Background serial reader that emits lines to an EventBus."""

    def __init__(
        self,
        port: str,
        baud: int = 115200,
        *,
        bus: EventBus | None = None,
        timestamp: bool = False,
    ) -> None:
        self.port = port
        self.baud = baud
        self.bus = bus
        self.timestamp = timestamp
        self._ser: serial.Serial | None = None  # type: ignore[name-defined]
        self._thread: threading.Thread | None = None
        self._stop = threading.Event()
        self._paused = threading.Event()
        self._paused.clear()
        self._lock = threading.Lock()
        self.on_line: Callable[[str], None] | None = None

    @property
    def is_open(self) -> bool:
        return self._ser is not None and self._ser.is_open

    def open(self) -> None:
        if serial is None:
            raise RuntimeError("pyserial is not installed")
        self._ser = serial.Serial(self.port, self.baud, timeout=0.2)
        self._stop.clear()
        self._thread = threading.Thread(target=self._read_loop, daemon=True)
        self._thread.start()

    def close(self) -> None:
        self._stop.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=2)
        with self._lock:
            if self._ser and self._ser.is_open:
                try:
                    self._ser.close()
                except Exception:  # noqa: BLE001
                    pass
            self._ser = None

    def pause(self) -> None:
        self._paused.set()

    def resume(self) -> None:
        self._paused.clear()

    def write(self, data: str | bytes) -> None:
        with self._lock:
            if not self._ser or not self._ser.is_open:
                raise RuntimeError("Serial port not open")
            payload = data.encode("utf-8", errors="replace") if isinstance(data, str) else data
            self._ser.write(payload)

    def _read_loop(self) -> None:
        assert self._ser is not None
        buf = ""
        while not self._stop.is_set():
            if self._paused.is_set():
                time.sleep(0.05)
                continue
            try:
                with self._lock:
                    raw = self._ser.read(256) if self._ser and self._ser.is_open else b""
            except Exception:  # noqa: BLE001
                break
            if not raw:
                continue
            try:
                text = raw.decode("utf-8", errors="replace")
            except Exception:  # noqa: BLE001
                text = repr(raw)
            buf += text
            while "\n" in buf:
                line, buf = buf.split("\n", 1)
                line = line.rstrip("\r")
                if self.timestamp:
                    line = f"{time.strftime('%H:%M:%S')} {line}"
                if self.on_line:
                    self.on_line(line)
                if self.bus:
                    self.bus.serial_line(line, port=self.port)


def attach_cli(
    port: str,
    baud: int = 115200,
    *,
    json_events: bool = False,
    bus: EventBus | None = None,
) -> int:
    """Attach to serial port; print lines until Ctrl-C. Returns exit code."""
    event_bus = bus or EventBus()

    def on_event(ev) -> None:  # noqa: ANN001
        if ev.type != "serial.line":
            return
        line = ev.payload.get("line", "")
        if json_events:
            print(ev.to_json(), flush=True)
        else:
            print(line, flush=True)

    event_bus.subscribe(on_event)
    mon = SerialMonitor(port, baud, bus=event_bus)
    try:
        mon.open()
    except Exception as e:  # noqa: BLE001
        print(f"Failed to open {port}: {e}", file=sys.stderr)
        return 5

    try:
        while True:
            time.sleep(0.2)
    except KeyboardInterrupt:
        pass
    finally:
        mon.close()
    return 0
