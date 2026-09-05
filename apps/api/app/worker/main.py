from __future__ import annotations

from app.core.config import get_settings
from app.core.logging import configure_logging
from app.worker.registry import WorkHandlerRegistry
from app.worker.runner import WorkerRunner


def main() -> None:
    settings = get_settings()
    configure_logging(settings.log_level)

    # Later modules register concrete handlers here through a small composition root.
    registry = WorkHandlerRegistry()
    WorkerRunner(registry=registry, settings=settings).run_forever()


if __name__ == "__main__":
    main()
