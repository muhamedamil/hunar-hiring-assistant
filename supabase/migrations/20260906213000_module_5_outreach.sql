begin;

create table public.outreach_requests (
    id uuid primary key default gen_random_uuid(),
    job_candidate_id uuid not null references public.job_candidates(id),
    decision_match_id uuid not null,
    phone_e164_snapshot text not null,
    screening_questions_snapshot jsonb not null,
    screening_context_hash char(64) not null,
    created_at timestamptz not null default now(),
    constraint fk_outreach_requests_decision_match
        foreign key (decision_match_id, job_candidate_id)
        references public.job_candidate_matches(id, job_candidate_id),
    constraint ck_outreach_requests_phone_e164
        check (phone_e164_snapshot ~ '^\+[1-9][0-9]{7,14}$'),
    constraint ck_outreach_requests_questions_array
        check (jsonb_typeof(screening_questions_snapshot) = 'array'),
    constraint ck_outreach_requests_question_count
        check (jsonb_array_length(screening_questions_snapshot) between 1 and 10),
    constraint ck_outreach_requests_hash_length
        check (char_length(screening_context_hash) = 64),
    constraint uq_outreach_requests_exact_context
        unique (
            job_candidate_id,
            decision_match_id,
            phone_e164_snapshot,
            screening_context_hash
        )
);

create or replace function public.prevent_outreach_request_mutation()
returns trigger
language plpgsql
set search_path = public, pg_temp
as $$
begin
    raise exception 'outreach request rows are immutable';
end;
$$;

revoke all on function public.prevent_outreach_request_mutation()
from public, anon, authenticated;

create trigger trg_outreach_requests_immutable
before update or delete on public.outreach_requests
for each row execute function public.prevent_outreach_request_mutation();

alter table public.outreach_requests enable row level security;
revoke all on table public.outreach_requests from anon, authenticated;

comment on table public.outreach_requests is
    'Module 5 immutable recruiter-confirmed phone and screening execution context.';
comment on column public.outreach_requests.phone_e164_snapshot is
    'Full canonical phone frozen for backend execution; never returned to normal browser reads.';
comment on column public.outreach_requests.screening_context_hash is
    'SHA-256 of ordered normalized screening semantics and exact Job-question provenance.';

commit;
