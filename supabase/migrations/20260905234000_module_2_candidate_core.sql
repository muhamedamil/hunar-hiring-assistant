begin;

create table public.candidates (
    id uuid primary key default gen_random_uuid(),
    full_name text not null,
    current_title text,
    current_company text,
    location text,
    email text,
    phone_e164 text,
    revision integer not null default 0 check (revision >= 0),
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),

    check (char_length(trim(full_name)) between 1 and 200),
    check (
        current_title is null
        or char_length(trim(current_title)) between 1 and 200
    ),
    check (
        current_company is null
        or char_length(trim(current_company)) between 1 and 200
    ),
    check (
        location is null
        or char_length(trim(location)) between 1 and 200
    ),
    check (
        email is null
        or char_length(trim(email)) between 3 and 320
    ),
    check (
        phone_e164 is null
        or phone_e164 ~ '^\+[1-9][0-9]{7,14}$'
    )
);

create unique index uq_candidates_email_ci
    on public.candidates (lower(email))
    where email is not null;

create unique index uq_candidates_phone_e164
    on public.candidates (phone_e164)
    where phone_e164 is not null;

create index ix_candidates_updated
    on public.candidates (updated_at desc);

create table public.candidate_external_identities (
    id uuid primary key default gen_random_uuid(),
    candidate_id uuid not null references public.candidates(id),
    provider text not null,
    external_person_id text not null,
    profile_url text,
    created_at timestamptz not null default now(),

    check (provider ~ '^[a-z][a-z0-9_]{1,39}$'),
    check (char_length(trim(external_person_id)) between 1 and 255),
    check (
        profile_url is null
        or char_length(trim(profile_url)) between 1 and 1000
    ),

    constraint uq_candidate_external_identities_provider_person
        unique (provider, external_person_id)
);

create index ix_candidate_external_identities_candidate
    on public.candidate_external_identities (candidate_id);

create or replace function public.prevent_candidate_external_identity_mutation()
returns trigger
language plpgsql
as $$
begin
    raise exception 'candidate_external_identities rows are immutable';
end;
$$;

create trigger trg_candidate_external_identities_immutable
before update or delete on public.candidate_external_identities
for each row
execute function public.prevent_candidate_external_identity_mutation();

revoke all on function public.prevent_candidate_external_identity_mutation()
from public, anon, authenticated;

alter table public.candidates enable row level security;
alter table public.candidate_external_identities enable row level security;

revoke all on table public.candidates from anon, authenticated;
revoke all on table public.candidate_external_identities from anon, authenticated;

comment on table public.candidates is
    'Global mutable Candidate identity/profile shared by manual and provider-sourced workflows.';

comment on column public.candidates.revision is
    'Optimistic-concurrency token incremented whenever Candidate aggregate truth changes.';

comment on column public.candidates.phone_e164 is
    'Canonical international E.164 phone number when known; null is valid before enrichment.';

comment on table public.candidate_external_identities is
    'Stable provider/person identity links pointing to the canonical Candidate record.';

commit;
