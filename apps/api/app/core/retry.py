from __future__ import annotations

import random
from dataclasses import dataclass


@dataclass(frozen=True)
class BackoffPolicy:
    base_seconds: float = 2.0
    max_seconds: float = 60.0
    jitter_ratio: float = 0.20

    def delay_seconds(self, attempt_count: int) -> float:
        if attempt_count < 1:
            raise ValueError("attempt_count must be >= 1")
        base_delay = min(self.max_seconds, self.base_seconds * (2 ** (attempt_count - 1)))
        jitter = base_delay * self.jitter_ratio
        noise = random.uniform(-jitter, jitter)
        return float(max(0.0, base_delay + noise))


class WorkExecutionError(Exception):
    def __init__(self, *, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


class RetryableWorkError(WorkExecutionError):
    def __init__(
        self,
        *,
        code: str,
        message: str,
        retry_after_seconds: float | None = None,
    ) -> None:
        super().__init__(code=code, message=message)
        self.retry_after_seconds = retry_after_seconds


class PermanentWorkError(WorkExecutionError):
    pass


class AmbiguousWorkError(WorkExecutionError):
    pass


class ProviderError(Exception):
    def __init__(
        self,
        *,
        code: str,
        message: str,
        status_code: int | None = None
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code


class ProviderAuthenticationError(ProviderError):
    pass


class ProviderPermanentError(ProviderError):
    pass


class ProviderTransientError(ProviderError):
    pass


class ProviderRateLimitError(ProviderTransientError):
    def __init__(self, *, retry_after_seconds: float | None, **kwargs) -> None:  # type: ignore[no-untyped-def]
        super().__init__(**kwargs)
        self.retry_after_seconds = retry_after_seconds


class ProviderTransportError(ProviderError):
    def __init__(self, *, operation_may_have_completed: bool, **kwargs) -> None:  # type: ignore[no-untyped-def]
        super().__init__(**kwargs)
        self.operation_may_have_completed = operation_may_have_completed


class ProviderInvalidResponseError(ProviderPermanentError):
    pass
