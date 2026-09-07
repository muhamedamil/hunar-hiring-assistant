export interface VoiceScreeningOptions {
  languages: "ENGLISH"[];
  default_language: "ENGLISH";
  timezones: string[];
  default_timezone: string;
  automatic_redials: false;
}

export interface VoiceCallExecution {
  id: string;
  outreach_request_id: string;
  status: "queued" | "submitted" | "failed" | "unknown";
  language: "ENGLISH";
  timezone: string;
  agent_contract_version: string;
  provider_call_id: string | null;
  provider_initial_status: string | null;
  failure_code: string | null;
  submitted_at: string | null;
  created_at: string;
  updated_at: string;
}
