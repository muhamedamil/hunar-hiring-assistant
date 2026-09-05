from __future__ import annotations

from typing import Protocol

from app.work_items.models import WorkItem


class WorkHandler(Protocol):
    def __call__(self, item: WorkItem) -> None: ...


class WorkHandlerRegistry:
    def __init__(self) -> None:
        self._handlers: dict[str, WorkHandler] = {}

    def register(self, work_type: str, handler: WorkHandler) -> None:
        if work_type in self._handlers:
            raise ValueError(f"Handler already registered for work type: {work_type}")
        self._handlers[work_type] = handler

    def get(self, work_type: str) -> WorkHandler | None:
        return self._handlers.get(work_type)

    def registered_types(self) -> tuple[str, ...]:
        return tuple(sorted(self._handlers))
