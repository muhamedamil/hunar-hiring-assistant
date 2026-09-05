begin;

create table public.work_items (
    id uuid primary key default gen_random_uuid(),

    work_type text not null,
    entity_type text,
    entity_id uuid,
    payload jsonb not null default '{}'::jsonb,

    status text not null default 'pending'
        check (
            status in (
                'pending',
                'running',
                'retry_scheduled',
                'succeeded',
                'failed',
                'unknown'
            )
        ),

    attempt_count integer not null default 0
        check (attempt_count >= 0),

    max_attempts integer not null default 3
        check (max_attempts >= 1),

    next_attempt_at timestamptz not null default now(),

    locked_at timestamptz,
    locked_by text,

    last_error_code text,
    last_error_message text,

    dedupe_key text,

    completed_at timestamptz,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),

    check (
        (status = 'running' and locked_at is not null and locked_by is not null)
        or
        (status <> 'running' and locked_at is null and locked_by is null)
    ),

    check (
        (status in ('succeeded', 'failed') and completed_at is not null)
        or
        (status not in ('succeeded', 'failed') and completed_at is null)
    )
);

create index ix_work_items_claim
    on public.work_items (next_attempt_at, created_at)
    where status in ('pending', 'retry_scheduled');

create index ix_work_items_running
    on public.work_items (locked_at)
    where status = 'running';

create unique index uq_work_items_active_dedupe
    on public.work_items (dedupe_key)
    where dedupe_key is not null
      and status in ('pending', 'running', 'retry_scheduled', 'unknown');

alter table public.work_items enable row level security;

revoke all on table public.work_items from anon, authenticated;

comment on table public.work_items is
    'Durable application work queue. UNKNOWN means execution outcome is ambiguous and must not auto-retry.';

comment on column public.work_items.dedupe_key is
    'Prevents duplicate active internal work only; does not guarantee provider-side exactly-once execution.';

commit;
