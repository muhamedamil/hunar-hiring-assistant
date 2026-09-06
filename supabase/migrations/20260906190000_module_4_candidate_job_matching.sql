begin;

create table public.job_candidates (
    id uuid primary key default gen_random_uuid(),
    job_id uuid not null references public.jobs(id),
    candidate_id uuid not null references public.candidates(id),
    created_source text not null,
    preferred_sourcing_result_id uuid references public.sourcing_results(id),
    shortlist_status text not null default 'reviewing',
    current_match_id uuid,
    decision_match_id uuid,
    revision integer not null default 0,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    constraint uq_job_candidates_job_candidate unique (job_id, candidate_id),
    constraint uq_job_candidates_identity_tuple unique (id, job_id, candidate_id),
    constraint ck_job_candidates_created_source
        check (created_source in ('manual','sourcing')),
    constraint ck_job_candidates_sourcing_has_source
        check (created_source = 'manual' or preferred_sourcing_result_id is not null),
    constraint ck_job_candidates_shortlist_status
        check (shortlist_status in ('reviewing','shortlisted','not_selected')),
    constraint ck_job_candidates_revision check (revision >= 0),
    constraint ck_job_candidates_decision_match_state
        check (
            (shortlist_status = 'reviewing' and decision_match_id is null)
            or (
                shortlist_status in ('shortlisted','not_selected')
                and decision_match_id is not null
            )
        )
);

create index ix_job_candidates_job_status_updated
    on public.job_candidates (job_id, shortlist_status, updated_at desc);
create index ix_job_candidates_candidate
    on public.job_candidates (candidate_id);

create table public.job_candidate_matches (
    id uuid primary key default gen_random_uuid(),
    job_candidate_id uuid not null,
    job_id uuid not null,
    candidate_id uuid not null,
    definition_version integer not null,
    source_sourcing_result_id uuid references public.sourcing_results(id),
    source_sourcing_run_id uuid references public.sourcing_runs(id),
    source_definition_version integer,
    source_evidence_version text,
    candidate_revision integer not null,
    input_snapshot jsonb not null,
    input_hash text not null,
    matcher_version text not null,
    analysis_key_hash text not null,
    analysis_mode text not null,
    status text not null,
    semantic_model text,
    semantic_prompt_version text,
    semantic_failure_code text,
    retry_after_seconds integer,
    match_score integer,
    evidence_coverage integer,
    match_reasons jsonb,
    started_at timestamptz not null default now(),
    completed_at timestamptz,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    constraint uq_job_candidate_matches_relation_identity
        unique (id, job_candidate_id),
    constraint fk_job_candidate_matches_relation
        foreign key (job_candidate_id, job_id, candidate_id)
        references public.job_candidates(id, job_id, candidate_id),
    constraint fk_job_candidate_matches_job_definition
        foreign key (job_id, definition_version)
        references public.job_definition_versions(job_id, version),
    constraint fk_job_candidate_matches_source_definition
        foreign key (job_id, source_definition_version)
        references public.job_definition_versions(job_id, version),
    constraint ck_candidate_matches_definition check (definition_version >= 1),
    constraint ck_candidate_matches_source_definition
        check (source_definition_version is null or source_definition_version >= 1),
    constraint ck_candidate_matches_source_provenance
        check (
            (source_sourcing_result_id is null
             and source_sourcing_run_id is null
             and source_definition_version is null
             and source_evidence_version is null)
            or
            (source_sourcing_result_id is not null
             and source_sourcing_run_id is not null
             and source_definition_version is not null)
        ),
    constraint ck_candidate_matches_revision check (candidate_revision >= 0),
    constraint ck_candidate_matches_input_object
        check (jsonb_typeof(input_snapshot) = 'object'),
    constraint ck_candidate_matches_hash_length
        check (char_length(input_hash) = 64 and char_length(analysis_key_hash) = 64),
    constraint ck_candidate_matches_analysis_mode
        check (analysis_mode in ('deterministic','hybrid_gemini','deterministic_fallback')),
    constraint ck_candidate_matches_status
        check (status in ('analyzing','completed','failed')),
    constraint ck_candidate_matches_retry_after
        check (retry_after_seconds is null or retry_after_seconds >= 0),
    constraint ck_candidate_matches_score
        check (match_score is null or match_score between 0 and 100),
    constraint ck_candidate_matches_coverage
        check (evidence_coverage is null or evidence_coverage between 0 and 100),
    constraint ck_candidate_matches_score_within_coverage
        check (
            match_score is null
            or evidence_coverage is null
            or match_score <= evidence_coverage
        ),
    constraint ck_candidate_matches_reasons_array
        check (match_reasons is null or jsonb_typeof(match_reasons) = 'array'),
    constraint ck_candidate_matches_completion_state
        check (
            (
                status = 'analyzing'
                and completed_at is null
                and match_score is null
                and evidence_coverage is null
                and match_reasons is null
            )
            or (
                status = 'completed'
                and completed_at is not null
                and match_score is not null
                and evidence_coverage is not null
                and match_reasons is not null
            )
            or (
                status = 'failed'
                and completed_at is not null
            )
        )
);

create unique index uq_candidate_matches_active_analysis
    on public.job_candidate_matches (job_candidate_id, analysis_key_hash)
    where status = 'analyzing';

create index ix_candidate_matches_relation_created
    on public.job_candidate_matches (job_candidate_id, created_at desc);

alter table public.job_candidates
    add constraint fk_job_candidates_current_match
        foreign key (current_match_id, id)
        references public.job_candidate_matches(id, job_candidate_id),
    add constraint fk_job_candidates_decision_match
        foreign key (decision_match_id, id)
        references public.job_candidate_matches(id, job_candidate_id);

create or replace function public.prevent_completed_job_candidate_match_mutation()
returns trigger
language plpgsql
set search_path = public, pg_temp
as $$
begin
    if old.status = 'completed' then
        raise exception 'completed job candidate match rows are immutable';
    end if;
    return new;
end;
$$;

revoke all on function public.prevent_completed_job_candidate_match_mutation() from public;
revoke all on function public.prevent_completed_job_candidate_match_mutation() from anon;
revoke all on function public.prevent_completed_job_candidate_match_mutation() from authenticated;

create trigger trg_job_candidate_matches_immutable
before update or delete on public.job_candidate_matches
for each row execute function public.prevent_completed_job_candidate_match_mutation();

alter table public.job_candidates enable row level security;
alter table public.job_candidate_matches enable row level security;

revoke all on table public.job_candidates from anon, authenticated;
revoke all on table public.job_candidate_matches from anon, authenticated;

comment on table public.job_candidates is
    'Module 4 stable Candidate-to-Job relationship and recruiter shortlist truth.';
comment on table public.job_candidate_matches is
    'Module 4 historical evidence-grounded match attempts bound to immutable Job versions.';
comment on column public.job_candidates.preferred_sourcing_result_id is
    'Explicit Module 3 evidence source selected for matching; may be attached after manual creation.';
comment on column public.job_candidate_matches.match_score is
    'Percentage of configured weighted Job criteria positively supported by available evidence.';
comment on column public.job_candidate_matches.evidence_coverage is
    'Percentage of configured weighted Job criteria that available evidence could evaluate.';

commit;
