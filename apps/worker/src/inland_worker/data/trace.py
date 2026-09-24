"""Tool-execution trace (spec §10 `tool_executions`). One record per data call; never contains secrets."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal, Protocol

from pydantic import BaseModel


class ToolExecution(BaseModel):
    job_id: str | None
    tool_name: str
    input: dict[str, Any]
    output_summary: dict[str, Any]
    started_at: datetime
    completed_at: datetime
    status: Literal["ok", "stale", "missing", "error"]
    error_code: str | None = None


class TraceSink(Protocol):
    def record(self, execution: ToolExecution) -> None: ...


class MemoryTraceSink:
    def __init__(self) -> None:
        self.records: list[ToolExecution] = []

    def record(self, execution: ToolExecution) -> None:
        self.records.append(execution)
