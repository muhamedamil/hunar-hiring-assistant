begin;

create table public.voice_call_executions (
    id uuid primary key default gen_random_uuid(),
    outreach_request_id uuid not null references public.outreach_requests(id),
    status text not null,
    agent_id uuid not null,
    language text not null,
    timezone text not null,
    agent_contract_version text not null,
    provider_request_id varchar(64) not null,
    provider_call_id uuid,
    provider_initial_status text,
    provider_payload_snapshot jsonb not null,
    failure_code text,
    submitted_at timestamptz,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    constraint uq_voice_call_executions_outreach unique (outreach_request_id),
    constraint uq_voice_call_executions_request unique (provider_request_id),
    constraint uq_voice_call_executions_call unique (provider_call_id),
    constraint ck_voice_call_executions_status check (status in ('queued','submitted','failed','unknown')),
    constraint ck_voice_call_executions_request_id check (provider_request_id ~ '^[A-Za-z0-9_.-]{1,64}$'),
    constraint ck_voice_call_executions_payload check (jsonb_typeof(provider_payload_snapshot) = 'object'),
    constraint ck_voice_call_executions_submission check ((status = 'submitted' and provider_call_id is not null and provider_initial_status is not null and submitted_at is not null) or (status in ('queued','failed') and provider_call_id is null and submitted_at is null) or (status = 'unknown' and submitted_at is null)),
    constraint ck_voice_call_executions_language check (language in ('ENGLISH','HINDI','TAMIL','TELUGU','KANNADA','MARATHI','MALAYALAM','GUJARATI','BENGALI','TURKISH','ARABIC','SPANISH')),
    constraint ck_voice_call_executions_timezone check (timezone in ('Asia/Kolkata','America/New_York','America/Los_Angeles','America/Chicago','America/Denver','America/Detroit','America/Kentucky/Louisville','America/Kentucky/Monticello','America/Indiana/Indianapolis','America/Indiana/Vincennes','America/Indiana/Winamac','America/Indiana/Marengo','America/Indiana/Petersburg','America/Indiana/Vevay','America/Indiana/Tell_City','America/Indiana/Knox','America/Menominee','America/North_Dakota/Center','America/North_Dakota/New_Salem','America/North_Dakota/Beulah','America/Boise','America/Phoenix','America/Anchorage','America/Juneau','America/Sitka','America/Metlakatla','America/Yakutat','America/Nome','America/Adak','Pacific/Honolulu','Asia/Riyadh','Europe/London')),
    constraint ck_voice_call_executions_provider_initial_status check (provider_initial_status in ('NOT_STARTED','SCHEDULED','INITIATED','RINGING','IN_PROGRESS','COMPLETED','NOT_CONNECTED','CANCELLED','FAILED'))
);

create function public.prevent_voice_call_input_mutation() returns trigger
language plpgsql set search_path = public, pg_temp as $$
begin
    if row(new.outreach_request_id, new.agent_id, new.language, new.timezone,
           new.agent_contract_version, new.provider_request_id, new.provider_payload_snapshot)
       is distinct from
       row(old.outreach_request_id, old.agent_id, old.language, old.timezone,
           old.agent_contract_version, old.provider_request_id, old.provider_payload_snapshot) then
        raise exception 'voice call execution inputs are immutable';
    end if;
    return new;
end;
$$;
revoke all on function public.prevent_voice_call_input_mutation() from public, anon, authenticated;
create trigger trg_voice_call_execution_inputs_immutable
before update on public.voice_call_executions
for each row execute function public.prevent_voice_call_input_mutation();
alter table public.voice_call_executions enable row level security;
revoke all on table public.voice_call_executions from anon, authenticated;
comment on table public.voice_call_executions is
    'Module 6 submission certainty only. Submitted is provider acceptance, not call completion.';
comment on column public.voice_call_executions.provider_request_id is
    'Correlation only; provider offers no idempotency guarantee. Never replay unknown.';
commit;
