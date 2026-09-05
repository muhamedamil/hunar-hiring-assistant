begin;

create table public.jobs (
    id uuid primary key default gen_random_uuid(),
    title text not null,
    company_name text,
    description text not null,
    requirements jsonb not null default '{}'::jsonb,
    screening_questions jsonb not null default '[]'::jsonb,
    status text not null default 'draft'
        check (status in ('draft', 'ready')),
    revision integer not null default 0
        check (revision >= 0),
    approved_version integer
        check (approved_version is null or approved_version >= 1),
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),

    check (char_length(trim(title)) between 1 and 200),
    check (
        company_name is null
        or char_length(trim(company_name)) between 1 and 200
    ),
    check (char_length(trim(description)) between 20 and 20000),
    check (jsonb_typeof(requirements) = 'object'),
    check (jsonb_typeof(screening_questions) = 'array'),
    check (status = 'draft' or approved_version is not null)
);

create index ix_jobs_status_updated
    on public.jobs (status, updated_at desc);

create index ix_jobs_created
    on public.jobs (created_at desc);

create table public.job_definition_versions (
    id uuid primary key default gen_random_uuid(),
    job_id uuid not null references public.jobs(id),
    version integer not null check (version >= 1),
    title text not null,
    company_name text,
    description text not null,
    requirements jsonb not null,
    screening_questions jsonb not null,
    created_at timestamptz not null default now(),

    unique (job_id, version),
    check (char_length(trim(title)) between 1 and 200),
    check (
        company_name is null
        or char_length(trim(company_name)) between 1 and 200
    ),
    check (char_length(trim(description)) between 20 and 20000),
    check (jsonb_typeof(requirements) = 'object'),
    check (jsonb_typeof(screening_questions) = 'array')
);

alter table public.jobs
    add constraint fk_jobs_approved_definition
    foreign key (id, approved_version)
    references public.job_definition_versions(job_id, version);

create or replace function public.prevent_job_definition_version_mutation()
returns trigger
language plpgsql
as $$
begin
    raise exception 'job_definition_versions rows are immutable';
end;
$$;

create trigger trg_job_definition_versions_immutable
before update or delete on public.job_definition_versions
for each row
execute function public.prevent_job_definition_version_mutation();

revoke all on function public.prevent_job_definition_version_mutation()
from public, anon, authenticated;

alter table public.jobs enable row level security;
alter table public.job_definition_versions enable row level security;

revoke all on table public.jobs from anon, authenticated;
revoke all on table public.job_definition_versions from anon, authenticated;

comment on table public.jobs is
    'Mutable working job definition. New downstream work may start only when status is ready.';

comment on column public.jobs.revision is
    'Optimistic-concurrency token incremented on every successful job aggregate mutation.';

comment on column public.jobs.approved_version is
    'Latest immutable approved definition version. DRAFT jobs may retain a prior approved version after reopen.';

comment on table public.job_definition_versions is
    'Immutable approved job-definition snapshots consumed by downstream sourcing, matching, and screening.';

commit;
