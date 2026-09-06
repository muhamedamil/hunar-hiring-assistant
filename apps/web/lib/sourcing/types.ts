export type SourcingRunStatus = "searching" | "completed" | "failed";

export type EnrichmentStatus =
  | "pending"
  | "awaiting_phone"
  | "completed"
  | "not_found"
  | "failed"
  | "unknown"
  | "conflict";

export type PhoneAvailability = "available" | "maybe" | "unavailable" | "unknown";

export interface UnmappedRequirement {
  field: string;
  values: string[];
}

export interface SourcingSearchCriteria {
  titles: string[];
  locations: string[];
  seniorities: string[];
  unmapped_requirements: UnmappedRequirement[];
  result_limit: number;
}

export interface ProviderSearchQuery {
  person_titles: string[];
  person_locations: string[];
  person_seniorities: string[];
  include_similar_titles: boolean;
  page: 1;
  per_page: number;
}

export interface SourcingResult {
  id: string;
  sourcing_run_id: string;
  provider_person_id: string;
  result_position: number;
  first_name: string | null;
  last_name_obfuscated: string | null;
  current_title: string | null;
  organization_name: string | null;
  email_available: boolean;
  phone_availability: PhoneAvailability;
  candidate_id: string | null;
  created_at: string;
}

export interface SourcingEnrichment {
  id: string;
  sourcing_result_id: string;
  provider: string;
  status: EnrichmentStatus;
  candidate_id: string | null;
  provider_request_id: number | null;
  credits_consumed: number | null;
  failure_code: string | null;
  retry_after_seconds: number | null;
  requested_at: string | null;
  completed_at: string | null;
  created_at: string;
  updated_at: string;
}

export interface SourcingRunSummary {
  id: string;
  job_id: string;
  definition_version: number;
  provider: string;
  status: SourcingRunStatus;
  result_limit: number;
  result_count: number;
  provider_total_matches: number | null;
  failure_code: string | null;
  retry_after_seconds: number | null;
  created_at: string;
  completed_at: string | null;
}

export interface SourcingRunListResponse {
  items: SourcingRunSummary[];
}

export interface SourcingRun extends SourcingRunSummary {
  criteria: SourcingSearchCriteria;
  provider_query: ProviderSearchQuery;
  mapping_version: string;
  attempt_count: number;
  started_at: string;
  updated_at: string;
  results: SourcingResult[];
  enrichments: SourcingEnrichment[];
}
