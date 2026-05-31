"""Severity-tagged logging that drives both the in-app log widget and disk logs."""

from __future__ import annotations

import datetime as _dt
import threading
from dataclasses import dataclass
from enum import IntEnum
from pathlib import Path
from typing import Callable, Iterable


class Severity(IntEnum):
    INFO = 10
    SECTION = 15
    TOOL = 20
    SUCCESS = 25
    WARN = 30
    ERROR = 40


_SEVERITY_NAMES = {
    Severity.INFO: "INFO",
    Severity.SECTION: "SECTION",
    Severity.TOOL: "TOOL",
    Severity.SUCCESS: "OK",
    Severity.WARN: "WARN",
    Severity.ERROR: "ERROR",
}


@dataclass(frozen=True)
class LogRecord:
    severity: Severity
    message: str
    timestamp: _dt.datetime

    def formatted(self) -> str:
        return f"[{self.timestamp:%H:%M:%S}] [{_SEVERITY_NAMES[self.severity]}] {self.message}"

    def tag(self) -> str:
        return {
            Severity.INFO: "info",
            Severity.SECTION: "section",
            Severity.TOOL: "tool",
            Severity.SUCCESS: "success",
            Severity.WARN: "warn",
            Severity.ERROR: "error",
        }[self.severity]


Listener = Callable[[LogRecord], None]


class Logger:
    """Thread-safe broadcast logger.

    Components emit messages via ``info``/``warn``/etc.; subscribers (UI log
    widget, on-disk file writer) receive every record. The log widget can also
    apply a runtime severity filter without affecting what gets written to disk.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._listeners: list[Listener] = []
        self._records: list[LogRecord] = []
        self._warn_count = 0
        self._error_count = 0

    # ---- emit ----
    def _emit(self, severity: Severity, message: str) -> None:
        record = LogRecord(severity, message, _dt.datetime.now())
        with self._lock:
            self._records.append(record)
            if severity == Severity.WARN:
                self._warn_count += 1
            elif severity == Severity.ERROR:
                self._error_count += 1
            listeners = list(self._listeners)
        for listener in listeners:
            try:
                listener(record)
            except Exception:
                # A failing listener must not break logging.
                pass

    def info(self, message: str) -> None:
        self._emit(Severity.INFO, message)

    def section(self, message: str) -> None:
        self._emit(Severity.SECTION, f"=== {message} ===")

    def tool(self, message: str) -> None:
        self._emit(Severity.TOOL, message)

    def success(self, message: str) -> None:
        self._emit(Severity.SUCCESS, message)

    def warn(self, message: str) -> None:
        self._emit(Severity.WARN, message)

    def error(self, message: str) -> None:
        self._emit(Severity.ERROR, message)

    # ---- subscribe ----
    def add_listener(self, listener: Listener) -> Callable[[], None]:
        with self._lock:
            self._listeners.append(listener)

        def unsubscribe() -> None:
            with self._lock:
                if listener in self._listeners:
                    self._listeners.remove(listener)

        return unsubscribe

    # ---- accessors ----
    def all_records(self) -> list[LogRecord]:
        with self._lock:
            return list(self._records)

    def counts(self) -> tuple[int, int]:
        with self._lock:
            return self._warn_count, self._error_count

    def reset_counts(self) -> None:
        with self._lock:
            self._warn_count = 0
            self._error_count = 0

    def clear(self) -> None:
        with self._lock:
            self._records.clear()
            self._warn_count = 0
            self._error_count = 0

    # ---- export ----
    def save_to(self, path: Path) -> None:
        records = self.all_records()
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", encoding="utf-8") as fh:
            for record in records:
                fh.write(record.formatted() + "\n")


SEVERITY_FILTERS = {
    "All": lambda r: True,
    "HideInfo": lambda r: r.severity != Severity.INFO,
    "WarnError": lambda r: r.severity >= Severity.WARN,
    "ErrorOnly": lambda r: r.severity >= Severity.ERROR,
}


def filtered(records: Iterable[LogRecord], filter_name: str) -> Iterable[LogRecord]:
    predicate = SEVERITY_FILTERS.get(filter_name, SEVERITY_FILTERS["All"])
    return (record for record in records if predicate(record))
