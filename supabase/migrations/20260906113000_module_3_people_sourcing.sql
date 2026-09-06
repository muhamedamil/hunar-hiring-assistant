begin;

create table public.sourcing_runs (
    id uuid primary key default gen_random_uuid(),
    job_id uuid not null,
    definition_version integer not null check (definition_version >= 1),
    provider text not null,
    status text not null default 'searching'
        check (status in ('searching', 'completed', 'failed')),
    criteria jsonb not null,
    provider_query jsonb not null,
    mapping_version text not null,
    result_limit integer not null check (result_limit between 1 and 50),
    result_count integer not null default 0 check (result_count >= 0),
    provider_total_matches bigint,
    attempt_count integer not null default 1 check (attempt_count >= 1),
    search_generation integer not null default 1 check (search_generation >= 1),
    failure_code text,
    retry_after_seconds integer check (retry_after_seconds is null or retry_after_seconds >= 0),
    started_at timestamptz not null default now(),
    completed_at timestamptz,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),

    constraint fk_sourcing_runs_job_definition
        foreign key (job_id, definition_version)
        references public.job_definition_versions(job_id, version),
    check (provider ~ '^[a-z][a-z0-9_]{1,39}$'),
    check (jsonb_typeof(criteria) = 'object'),
    check (jsonb_typeof(provider_query) = 'object'),
    check (result_count <= result_limit),
    check (
        (status = 'completed' and completed_at is not null)
        or (status <> 'completed')
    )
);

create index ix_sourcing_runs_job_created
    on public.sourcing_runs (job_id, created_at desc);

create index ix_sourcing_runs_status_updated
    on public.sourcing_runs (status, updated_at desc);

create table public.sourcing_results (
    id uuid primary key default gen_random_uuid(),
    sourcing_run_id uuid not null references public.sourcing_runs(id) on delete cascade,
    provider_person_id text not null,
    result_position integer not null check (result_position >= 1),
    first_name text,
    last_name_obfuscated text,
    current_title text,
    organization_name text,
    email_available boolean not null default false,
    phone_availability text not null default 'unknown'
        check (phone_availability in ('available', 'maybe', 'unavailable', 'unknown')),
    provider_last_refreshed_at timestamptz,
    candidate_id uuid references public.candidates(id),
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),

    constraint uq_sourcing_results_run_person
        unique (sourcing_run_id, provider_person_id),
    constraint uq_sourcing_results_run_position
        unique (sourcing_run_id, result_position),
    check (char_length(trim(provider_person_id)) between 1 and 255)
);

create index ix_sourcing_results_run_position
    on public.sourcing_results (sourcing_run_id, result_position);

create index ix_sourcing_results_candidate
    on public.sourcing_results (candidate_id)
    where candidate_id is not null;

create table public.sourcing_enrichments (
    id uuid primary key default gen_random_uuid(),
    sourcing_result_id uuid not null references public.sourcing_results(id) on delete cascade,
    provider text not null,
    status text not null default 'pending'
        check (
            status in (
                'pending',
                'awaiting_phone',
                'completed',
                'not_found',
                'failed',
                'unknown',
                'conflict'
            )
        ),
    candidate_id uuid references public.candidates(id),
    provider_request_id bigint,
    attempt_count integer not null default 0 check (attempt_count >= 0),
    credits_consumed integer check (credits_consumed is null or credits_consumed >= 0),
    failure_code text,
    retry_after_seconds integer check (retry_after_seconds is null or retry_after_seconds >= 0),
    requested_at timestamptz,
    completed_at timestamptz,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),

    constraint uq_sourcing_enrichments_result unique (sourcing_result_id),
    check (provider ~ '^[a-z][a-z0-9_]{1,39}$'),
    check (
        (status in ('completed', 'not_found', 'failed', 'unknown', 'conflict')
         and completed_at is not null)
        or
        (status not in ('completed', 'not_found', 'failed', 'unknown', 'conflict'))
    )
);

create unique index uq_sourcing_enrichments_provider_request
    on public.sourcing_enrichments (provider_request_id)
    where provider_request_id is not null;

create index ix_sourcing_enrichments_status_updated
    on public.sourcing_enrichments (status, updated_at desc);

alter table public.sourcing_runs enable row level security;
alter table public.sourcing_results enable row level security;
alter table public.sourcing_enrichments enable row level security;

revoke all on table public.sourcing_runs from anon, authenticated;
revoke all on table public.sourcing_results from anon, authenticated;
revoke all on table public.sourcing_enrichments from anon, authenticated;

comment on table public.sourcing_runs is
    'Historical provider-search execution bound to one immutable approved Job definition version.';

comment on table public.sourcing_results is
    'Provider search evidence only. A search result is not canonical Candidate truth.';

comment on table public.sourcing_enrichments is
    'One logical credit-aware enrichment operation for one sourcing result.';

comment on column public.sourcing_runs.provider_query is
    'Exact provider query used for historical reproducibility; retries reuse this value.';

comment on column public.sourcing_enrichments.provider_request_id is
    'Apollo signed 64-bit request ID used for webhook/poll recovery; may be negative.';

commit;
