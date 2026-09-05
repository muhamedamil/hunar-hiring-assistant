export interface CandidateExternalIdentity {
  id: string;
  provider: string;
  external_person_id: string;
  profile_url: string | null;
  created_at: string;
}

export interface CandidateProfileInput {
  full_name: string;
  current_title: string | null;
  current_company: string | null;
  location: string | null;
  email: string | null;
  phone: string | null;
}

export interface Candidate {
  id: string;
  full_name: string;
  current_title: string | null;
  current_company: string | null;
  location: string | null;
  email: string | null;
  phone_e164: string | null;
  external_identities: CandidateExternalIdentity[];
  revision: number;
  created_at: string;
  updated_at: string;
}

export interface CandidateSummary {
  id: string;
  full_name: string;
  current_title: string | null;
  current_company: string | null;
  location: string | null;
  has_email: boolean;
  has_phone: boolean;
  revision: number;
  updated_at: string;
}

export interface CandidateListResponse {
  items: CandidateSummary[];
  limit: number;
  offset: number;
}
