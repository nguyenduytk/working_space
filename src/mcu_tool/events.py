"""Structured event bus for jobs and logging."""

from __future__ import annotations

import json
import threading
import time
from dataclasses import asdict, dataclass, field
from typing import Any, Callable


EventHandler = Callable[["Event"], None]


@dataclass
class Event:
    type: str
    payload: dict[str, Any] = field(default_factory=dict)
    ts: float = field(default_factory=time.time)

    def to_dict(self) -> dict[str, Any]:
        return {"type": self.type, "ts": self.ts, **self.payload}

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False)


class EventBus:
    """Thread-safe pub/sub for job and log events."""

    def __init__(self) -> None:
        self._handlers: list[EventHandler] = []
        self._lock = threading.Lock()

    def subscribe(self, handler: EventHandler) -> None:
        with self._lock:
            self._handlers.append(handler)

    def unsubscribe(self, handler: EventHandler) -> None:
        with self._lock:
            if handler in self._handlers:
                self._handlers.remove(handler)

    def emit(self, event_type: str, **payload: Any) -> Event:
        event = Event(type=event_type, payload=payload)
        with self._lock:
            handlers = list(self._handlers)
        for h in handlers:
            try:
                h(event)
            except Exception:  # noqa: BLE001 — never break emitters
                pass
        return event

    def job_started(self, job_id: str, action: str, project_id: str | None = None) -> Event:
        return self.emit(
            "job.started",
            job_id=job_id,
            action=action,
            project_id=project_id,
        )

    def log_line(self, line: str, stream: str = "stdout", job_id: str | None = None) -> Event:
        return self.emit(
            "log.line",
            line=line.rstrip("\n"),
            stream=stream,
            job_id=job_id,
        )

    def job_finished(
        self,
        job_id: str,
        ok: bool,
        exit_code: int,
        message: str = "",
        artifact: str | None = None,
    ) -> Event:
        return self.emit(
            "job.finished",
            job_id=job_id,
            ok=ok,
            exit_code=exit_code,
            message=message,
            artifact=artifact,
        )

    def serial_line(self, line: str, port: str | None = None) -> Event:
        return self.emit("serial.line", line=line.rstrip("\n"), port=port)
