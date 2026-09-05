from __future__ import annotations

from app.core.retry import BackoffPolicy


def test_backoff_is_exponential_without_jitter() -> None:
    policy = BackoffPolicy(base_seconds=2, max_seconds=60, jitter_ratio=0)
    assert policy.delay_seconds(1) == 2
    assert policy.delay_seconds(2) == 4
    assert policy.delay_seconds(3) == 8


def test_backoff_is_capped() -> None:
    policy = BackoffPolicy(base_seconds=10, max_seconds=15, jitter_ratio=0)
    assert policy.delay_seconds(3) == 15
