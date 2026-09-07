"""Exact provider payload, contract drift, transport and response certainty qualification."""

import json
from pathlib import Path
from uuid import uuid4

import httpx
import pytest
from pydantic import ValidationError

from app.core.config import Settings
from app.core.retry import ProviderInvalidResponseError, ProviderTransportError
from app.integrations.hunar.client import HunarVoiceProvider
from app.integrations.hunar.errors import HunarAmbiguousResponseError
from app.integrations.hunar.schemas import (
    HunarAgentDetail,
    HunarCallCreateCommand,
    HunarLanguage,
    HunarRetryConfig,
    HunarTimezone,
)
from app.voice_calls.agent_contract import get_contract
from app.voice_calls.errors import VoiceCallError

AGENT_ID = uuid4()


def agent_payload():
    contract = get_contract()
    return dict(
        id=str(AGENT_ID),
        status="ACTIVE",
        language="ENGLISH",
        voice_persona="NEHA",
        persona_name="Maya",
        custom_variables=sorted(contract.custom_variables),
        objective=contract.objective,
        introduction=contract.introduction,
        agent_prompt=contract.agent_prompt,
        result_prompt=contract.result_prompt,
        result_schema=json.loads(contract.result_schema_json),
    )


def command():
    return HunarCallCreateCommand(
        agent_id=AGENT_ID,
        callee_name="Controlled Test",
        mobile_number="+12025550123",
        custom_data={
            "job_role": "Engineer",
            "role_context": "Role title: Engineer",
            "screening_plan": "Question 1\nPrompt: Are you interested?",
        },
        request_id="hha-" + uuid4().hex,
        timezone=HunarTimezone.ASIA_KOLKATA,
        retry_config=HunarRetryConfig(),
    )


def response_payload(cmd):
    return dict(
        id=str(uuid4()),
        request_id=cmd.request_id,
        status="SCHEDULED",
        callee_name=cmd.callee_name,
        mobile_number=cmd.mobile_number,
        timezone=cmd.timezone.value,
    )


def provider(handler):
    return HunarVoiceProvider(
        api_key="test-key",
        base_url="https://hunar.example/external/v1",
        transport=httpx.MockTransport(handler),
    )


def test_frozen_contract_matches_independent_plan_text_and_schema():
    import re

    plan = (
        Path(__file__).resolve().parents[3] / "doc/MODULE_6_IMPLEMENTATION_PLAN.md"
    ).read_text(encoding="utf-8")
    contract = get_contract()
    for title, field in [
        ("Objective", "objective"),
        ("Introduction", "introduction"),
        ("Agent prompt", "agent_prompt"),
        ("Result prompt", "result_prompt"),
    ]:
        expected = re.search(r"#### " + title + r"\n.*?```text\n(.*?)\n```", plan, re.S)[1]
        assert getattr(contract, field) == expected
    assert contract.version == "hunar_voice_screening_en_v1"
    assert contract.voice_persona == "NEHA" and contract.persona_name == "Maya"
    schema = json.loads(re.search(r"#### Result schema\n.*?```json\n(.*?)\n```", plan, re.S)[1])
    assert json.loads(contract.result_schema_json) == schema


@pytest.mark.parametrize(
    "field,value",
    [
        ("id", str(uuid4())),
        ("status", "DRAFT"),
        ("status", "ARCHIVED"),
        ("language", "HINDI"),
        ("voice_persona", "ROY"),
        ("persona_name", "Mira"),
        ("custom_variables", ["job_role", "role_context"]),
        ("custom_variables", ["job_role", "role_context", "screening_plan", "extra"]),
        ("objective", "changed"),
        ("introduction", "changed"),
        ("agent_prompt", "changed"),
        ("result_prompt", "changed"),
        ("result_schema", {"qualified": ""}),
        ("objective", None),
        ("result_prompt", None),
    ],
)
def test_every_contract_field_fails_closed(field, value):
    raw = agent_payload()
    raw[field] = value
    with pytest.raises(VoiceCallError):
        get_contract().validate(HunarAgentDetail.model_validate(raw), AGENT_ID)


def test_only_line_endings_and_outer_whitespace_normalized():
    raw = agent_payload()
    for field in ("objective", "introduction", "agent_prompt", "result_prompt", "persona_name"):
        raw[field] = " \r\n" + raw[field].replace("\n", "\r\n") + "\r\n "
    get_contract().validate(HunarAgentDetail.model_validate(raw), AGENT_ID)
    raw["agent_prompt"] = raw["agent_prompt"].replace("warm, professional", "warm,  professional")
    with pytest.raises(VoiceCallError):
        get_contract().validate(HunarAgentDetail.model_validate(raw), AGENT_ID)


def test_exact_paths_header_payload_and_no_automatic_transport_retry():
    cmd = command()
    seen = []

    def handle(request):
        seen.append(request)
        assert request.headers["X-API-Key"] == "test-key"
        if request.method == "GET":
            assert request.url.path == f"/external/v1/agents/{AGENT_ID}/"
            return httpx.Response(200, json=agent_payload())
        assert request.url.path == "/external/v1/calls/"
        body = json.loads(request.content)
        assert set(body) == {
            "agent_id",
            "callee_name",
            "mobile_number",
            "custom_data",
            "request_id",
            "timezone",
            "retry_config",
        }
        assert body["retry_config"] == {"max_retry_count": 0, "retry_interval_hours": 0}
        assert set(body["custom_data"]) == {"job_role", "role_context", "screening_plan"}
        assert all(isinstance(v, str) for v in body["custom_data"].values())
        return httpx.Response(200, json=response_payload(cmd))

    client = provider(handle)
    client.get_agent(AGENT_ID)
    client.create_call(cmd)
    assert len(seen) == 2
    client.close()


@pytest.mark.parametrize(
    "field,value",
    [
        ("id", "invalid"),
        ("request_id", "wrong"),
        ("status", "unexpected"),
        ("callee_name", "other"),
        ("mobile_number", "+12025550124"),
        ("timezone", "Europe/London"),
    ],
)
def test_inconsistent_acceptance_unknown_retains_valid_identity(field, value):
    cmd = command()
    raw = response_payload(cmd)
    call_id = raw["id"]
    raw[field] = value
    client = provider(lambda _: httpx.Response(200, json=raw))
    with pytest.raises(HunarAmbiguousResponseError) as caught:
        client.create_call(cmd)
    assert (str(caught.value.call_id) == call_id) if field != "id" else caught.value.call_id is None
    assert cmd.mobile_number not in str(caught.value)
    client.close()


@pytest.mark.parametrize(
    "field", ["id", "request_id", "status", "callee_name", "mobile_number", "timezone"]
)
def test_missing_required_success_field_is_ambiguous(field):
    cmd = command()
    raw = response_payload(cmd)
    del raw[field]
    client = provider(lambda _: httpx.Response(200, json=raw))
    with pytest.raises(HunarAmbiguousResponseError):
        client.create_call(cmd)
    client.close()


@pytest.mark.parametrize(
    "error,safe",
    [
        (httpx.ConnectError, True),
        (httpx.ConnectTimeout, True),
        (httpx.ReadTimeout, False),
        (httpx.WriteTimeout, False),
        (httpx.RemoteProtocolError, False),
    ],
)
def test_transport_certainty_no_adapter_retries(error, safe):
    calls = []

    def handle(request):
        calls.append(request)
        raise error("synthetic")

    client = provider(handle)
    with pytest.raises(ProviderTransportError) as caught:
        client.create_call(command())
    assert caught.value.operation_may_have_completed is not safe
    assert len(calls) == 1
    client.close()


def test_invalid_json_is_not_replayed():
    client = provider(lambda _: httpx.Response(200, content=b"not json"))
    with pytest.raises(ProviderInvalidResponseError):
        client.create_call(command())
    client.close()


def test_outbound_extra_fields_and_invalid_custom_data_rejected():
    raw = command().model_dump(mode="json")
    for field in ("from_phone_number", "guardrails", "call_status_callback_url"):
        with pytest.raises(ValidationError):
            HunarCallCreateCommand.model_validate({**raw, field: "unwanted"})
    with pytest.raises(ValidationError):
        HunarCallCreateCommand.model_validate({**raw, "custom_data": {"job_role": 12}})
    for retry in (
        {"max_retry_count": 1, "retry_interval_hours": 0},
        {"max_retry_count": 0, "retry_interval_hours": 1},
    ):
        with pytest.raises(ValidationError):
            HunarCallCreateCommand.model_validate({**raw, "retry_config": retry})


def test_settings_mapping_timezones_and_callback():
    settings = Settings(
        database_url="postgresql://test",
        hunar_api_key="  ",
        hunar_call_summary_callback_url=" ",
        hunar_screening_agent_ids_json=json.dumps({"ENGLISH": str(AGENT_ID)}),
    )
    assert settings.hunar_api_key is None and settings.hunar_call_summary_callback_url is None
    assert settings.hunar_agent_ids == {HunarLanguage.ENGLISH: AGENT_ID}
    assert len(HunarTimezone) == 32
    for kwargs in (
        {"hunar_default_language": "HINDI"},
        {"hunar_default_timezone": "UTC"},
        {"hunar_api_base_url": "http://insecure.example"},
        {"hunar_screening_agent_ids_json": '{"HINDI":"' + str(AGENT_ID) + '"}'},
    ):
        with pytest.raises(ValidationError):
            Settings(database_url="postgresql://test", **kwargs)
    raw = command().model_dump(mode="json")
    raw["callback_config"] = {"call_summary_callback_url": "https://receiver.example/summary/"}
    assert (
        HunarCallCreateCommand.model_validate(raw).model_dump(mode="json", exclude_none=True)[
            "callback_config"
        ]
        == raw["callback_config"]
    )


def test_provider_enum_and_required_response_parity_against_captured_openapi():
    from app.integrations.hunar.schemas import (
        HunarAgentStatus,
        HunarCallCreateResponse,
        HunarCallStatus,
        HunarVoicePersona,
    )

    schema = json.loads(
        (Path(__file__).parent / "fixtures/hunar_external_v1_contract.json").read_text(
            encoding="utf-8"
        )
    )["schemas"]
    for enum, key in [
        (HunarLanguage, "VoiceCallLanguage"),
        (HunarTimezone, "Timezone"),
        (HunarVoicePersona, "VoicePersona"),
        (HunarAgentStatus, "AgentStatus"),
        (HunarCallStatus, "CallStatus"),
    ]:
        assert [item.value for item in enum] == schema[key]["enum"]
    required = {
        name for name, field in HunarCallCreateResponse.model_fields.items() if field.is_required()
    }
    assert required == set(schema["CallCreateResponseSchema"]["required"])


def test_model_checks_are_exact_migration_checks_without_schema_creation():
    from sqlalchemy import CheckConstraint

    from app.voice_calls.models import VoiceCallExecution

    migration = (
        Path(__file__).resolve().parents[3]
        / "supabase/migrations/20260907113000_module_6_hunar_voice_execution.sql"
    ).read_text(encoding="utf-8")
    assert len(VoiceCallExecution.__table__.columns) == 15
    for check in VoiceCallExecution.__table__.constraints:
        if isinstance(check, CheckConstraint):
            assert f"constraint {check.name} check ({check.sqltext})" in migration
    assert "provider_initial_status text" in migration
    assert "provider_call_id uuid" in migration


def test_callback_client_sends_only_configured_summary():
    cmd = command().model_copy(update={})
    raw = cmd.model_dump(mode="json")
    raw["callback_config"] = {"call_summary_callback_url": "https://receiver.example/summary/"}
    cmd = HunarCallCreateCommand.model_validate(raw)

    def handle(request):
        assert json.loads(request.content)["callback_config"] == raw["callback_config"]
        return httpx.Response(200, json=response_payload(cmd))

    client = provider(handle)
    client.create_call(cmd)
    client.close()
