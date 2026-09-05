from __future__ import annotations

from app.work_items.repository import WorkItemRepository
from app.work_items.schemas import WorkItemCreate


class WorkItemService:
    def __init__(self, repository: WorkItemRepository | None = None) -> None:
        self.repository = repository or WorkItemRepository()

    def enqueue(self, session, command: WorkItemCreate):  # type: ignore[no-untyped-def]
        return self.repository.enqueue(session, command)
