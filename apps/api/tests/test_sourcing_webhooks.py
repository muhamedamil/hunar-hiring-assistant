"""Module 3 webhook security and deterministic phone-selection tests."""

from __future__ import annotations

from uuid import uuid4

import pytest

from app.sourcing.errors import ApolloWebhookSignatureError
from app.sourcing.schemas import ProviderPhoneNumber
from app.sourcing.webhooks import (
    SourcingWebhookService,
    sign_apollo_webhook,
    verify_apollo_webhook_signature,
)


def test_webhook_signature_is_enrichment_specific_and_constant_contract() -> None:
    enrichment_id = uuid4()
    signature = sign_apollo_webhook("test-secret", enrichment_id)

    verify_apollo_webhook_signature(
        secret="test-secret",
        enrichment_id=enrichment_id,
        signature=signature,
    )

    with pytest.raises(ApolloWebhookSignatureError):
        verify_apollo_webhook_signature(
            secret="wrong-secret",
            enrichment_id=enrichment_id,
            signature=signature,
        )


def test_phone_selection_prefers_valid_mobile_then_work_direct() -> None:
    pytest.importorskip("phonenumbers")
    phones = [
        ProviderPhoneNumber(
            raw_number="+1 202-555-0142",
            sanitized_number="+12025550142",
            type_code="work_direct",
            status_code="valid_number",
            position=0,
        ),
        ProviderPhoneNumber(
            raw_number="+1 202-555-0116",
            sanitized_number="+12025550116",
            type_code="mobile",
            status_code="valid_number",
            position=1,
        ),
    ]

    selected = SourcingWebhookService._select_phone(phones)  # noqa: SLF001

    assert selected == "+12025550116"


def test_phone_selection_ignores_provider_values_that_fail_candidate_normalization() -> None:
    pytest.importorskip("phonenumbers")
    phones = [
        ProviderPhoneNumber(
            sanitized_number="+10000000000",
            type_code="mobile",
            status_code="valid_number",
            position=0,
        )
    ]

    assert SourcingWebhookService._select_phone(phones) is None  # noqa: SLF001


def test_phone_selection_does_not_hide_normalization_runtime_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A missing/broken phone runtime must not be converted into false completed business truth."""

    def fail_runtime(value: object) -> object:
        del value
        raise RuntimeError("phone normalization runtime unavailable")

    monkeypatch.setattr("app.sourcing.webhooks.normalize_phone_e164", fail_runtime)
    phones = [
        ProviderPhoneNumber(
            sanitized_number="+12025550116",
            type_code="mobile",
            status_code="valid_number",
            position=0,
        )
    ]

    with pytest.raises(RuntimeError, match="phone normalization runtime unavailable"):
        SourcingWebhookService._select_phone(phones)  # noqa: SLF001
