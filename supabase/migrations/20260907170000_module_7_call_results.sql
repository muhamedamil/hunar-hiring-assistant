begin;

create table public.voice_call_results (
    id uuid primary key default gen_random_uuid(),
    voice_call_execution_id uuid not null references public.voice_call_executions(id),
    provider_call_id uuid not null,
    provider_status text not null,
    lifecycle_status text not null,
    answered_by text,
    screening_result_state text not null,
    result_failure_code text,
    conversation_outcome text,
    candidate_interest text,
    notes text,
    duration_seconds double precision,
    started_at timestamptz,
    ended_at timestamptz,
    recording_url text,
    observed_at timestamptz not null,
    updated_at timestamptz not null,
    constraint uq_voice_call_results_execution unique (voice_call_execution_id),
    constraint uq_voice_call_results_provider_call unique (provider_call_id),
    constraint ck_voice_call_results_provider_status check
        (provider_status in ('COMPLETED','NOT_CONNECTED','FAILED','CANCELLED')),
    constraint ck_voice_call_results_lifecycle check
        (lifecycle_status in ('COMPLETED','NOT_CONNECTED','FAILED','CANCELLED')),
    constraint ck_voice_call_results_answered_by check
        (answered_by is null or answered_by in ('HUMAN','MACHINE','UNKNOWN')),
    constraint ck_voice_call_results_state check
        (screening_result_state in ('available','unavailable','invalid')),
    constraint ck_voice_call_results_outcome check
        (conversation_outcome is null or conversation_outcome in
         ('completed','partial','not_interested','wrong_person','not_available',
          'disconnected','other')),
    constraint ck_voice_call_results_interest check
        (candidate_interest is null or candidate_interest in
         ('interested','not_interested','unclear')),
    constraint ck_voice_call_results_duration check
        (duration_seconds is null or duration_seconds >= 0),
    constraint ck_voice_call_results_timing check
        (started_at is null or ended_at is null or ended_at >= started_at),
    constraint ck_voice_call_results_available check
        (screening_result_state <> 'available' or
         (lifecycle_status = 'COMPLETED' and answered_by = 'HUMAN' and
          conversation_outcome is not null and candidate_interest is not null and
          result_failure_code is null)),
    constraint ck_voice_call_results_unavailable_lifecycle check
        (lifecycle_status = 'COMPLETED' or
         (screening_result_state = 'unavailable' and conversation_outcome is null and
          candidate_interest is null)),
    constraint ck_voice_call_results_nonhuman check
        (answered_by is null or answered_by = 'HUMAN' or
         screening_result_state <> 'available')
);

create table public.voice_screening_answers (
    id uuid primary key default gen_random_uuid(),
    voice_call_result_id uuid not null references public.voice_call_results(id),
    outreach_question_id uuid not null,
    position smallint not null,
    answer_state text not null,
    answer_text text,
    created_at timestamptz not null default now(),
    constraint uq_voice_screening_answers_position
        unique (voice_call_result_id, position),
    constraint uq_voice_screening_answers_question
        unique (voice_call_result_id, outreach_question_id),
    constraint ck_voice_screening_answers_position check (position between 1 and 10),
    constraint ck_voice_screening_answers_state check
        (answer_state in ('answered','no_clear_answer','not_asked')),
    constraint ck_voice_screening_answers_text check
        ((answer_state = 'answered' and nullif(btrim(answer_text), '') is not null) or
         (answer_state in ('no_clear_answer','not_asked') and answer_text is null))
);

create function public.guard_voice_call_result_mutation() returns trigger
language plpgsql set search_path = public, pg_temp as $$
begin
    if row(new.voice_call_execution_id, new.provider_call_id, new.provider_status,
           new.lifecycle_status, new.observed_at)
       is distinct from
       row(old.voice_call_execution_id, old.provider_call_id, old.provider_status,
           old.lifecycle_status, old.observed_at) then
        raise exception 'voice call terminal identity is immutable';
    end if;
    if (old.answered_by is not null and new.answered_by is distinct from old.answered_by)
       or (old.duration_seconds is not null and
           new.duration_seconds is distinct from old.duration_seconds)
       or (old.started_at is not null and new.started_at is distinct from old.started_at)
       or (old.ended_at is not null and new.ended_at is distinct from old.ended_at) then
        raise exception 'known terminal evidence cannot conflict';
    end if;
    if old.screening_result_state = 'available' and
       row(new.screening_result_state, new.result_failure_code, new.conversation_outcome,
           new.candidate_interest, new.notes)
       is distinct from
       row(old.screening_result_state, old.result_failure_code, old.conversation_outcome,
           old.candidate_interest, old.notes) then
        raise exception 'available screening result is immutable';
    end if;
    if old.screening_result_state <> 'available' and
       new.screening_result_state not in (old.screening_result_state, 'available') then
        raise exception 'screening result transition is not monotonic';
    end if;
    return new;
end;
$$;
revoke all on function public.guard_voice_call_result_mutation() from public, anon, authenticated;
create trigger trg_voice_call_result_mutation_guard
before update on public.voice_call_results
for each row execute function public.guard_voice_call_result_mutation();

create function public.prevent_voice_screening_answer_mutation() returns trigger
language plpgsql set search_path = public, pg_temp as $$
begin
    raise exception 'voice screening answers are immutable';
end;
$$;
revoke all on function public.prevent_voice_screening_answer_mutation()
from public, anon, authenticated;
create trigger trg_voice_screening_answers_immutable
before update or delete on public.voice_screening_answers
for each row execute function public.prevent_voice_screening_answer_mutation();

alter table public.voice_call_results enable row level security;
alter table public.voice_screening_answers enable row level security;
revoke all on table public.voice_call_results from anon, authenticated;
revoke all on table public.voice_screening_answers from anon, authenticated;
comment on table public.voice_call_results is
    'Module 7 terminal call and screening-result truth; Module 6 status remains independent.';
comment on column public.voice_call_results.recording_url is
    'Backend-only provider reference. Public APIs expose only recording availability.';
comment on table public.voice_screening_answers is
    'Immutable answer mapping to exact Module 5 outreach question UUIDs.';

commit;
