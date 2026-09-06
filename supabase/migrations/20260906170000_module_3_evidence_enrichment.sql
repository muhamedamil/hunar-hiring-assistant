begin;

alter table public.sourcing_enrichments
    add column professional_evidence jsonb,
    add column evidence_version text,
    add constraint ck_sourcing_enrichments_professional_evidence_object
        check (
            professional_evidence is null
            or jsonb_typeof(professional_evidence) = 'object'
        ),
    add constraint ck_sourcing_enrichments_professional_evidence_version
        check (
            (professional_evidence is null) = (evidence_version is null)
        );

comment on column public.sourcing_enrichments.professional_evidence is
    'Normalized non-contact professional evidence from the existing enrichment response.';

comment on column public.sourcing_enrichments.evidence_version is
    'Version of the provider-neutral professional-evidence normalization contract.';

commit;
