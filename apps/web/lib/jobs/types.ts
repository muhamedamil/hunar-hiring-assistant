export type JobStatus = "draft" | "ready";

export type SeniorityLevel =
  | "intern"
  | "entry"
  | "mid"
  | "senior"
  | "lead"
  | "manager"
  | "director"
  | "executive";

export type EmploymentType =
  | "full_time"
  | "part_time"
  | "contract"
  | "internship"
  | "temporary"
  | "other";

export type WorkArrangement = "onsite" | "hybrid" | "remote";

export type ScreeningAnswerType = "yes_no" | "short_text" | "number" | "choice";

export interface JobRequirements {
  alternate_titles: string[];
  required_skills: string[];
  preferred_skills: string[];
  locations: string[];
  min_years_experience: number | null;
  seniority: SeniorityLevel[];
  employment_type: EmploymentType | null;
  work_arrangement: WorkArrangement | null;
}

export interface ScreeningQuestion {
  id: string;
  key: string;
  prompt: string;
  answer_type: ScreeningAnswerType;
  required: boolean;
  options: string[];
}

export interface ScreeningQuestionInput {
  id?: string;
  key: string;
  prompt: string;
  answer_type: ScreeningAnswerType;
  required: boolean;
  options: string[];
}

export interface JobDefinitionInput {
  title: string;
  company_name: string | null;
  description: string;
  requirements: JobRequirements;
  screening_questions: ScreeningQuestionInput[];
}

export interface Job {
  id: string;
  title: string;
  company_name: string | null;
  description: string;
  requirements: JobRequirements;
  screening_questions: ScreeningQuestion[];
  status: JobStatus;
  revision: number;
  approved_version: number | null;
  created_at: string;
  updated_at: string;
}

export interface JobSummary {
  id: string;
  title: string;
  company_name: string | null;
  status: JobStatus;
  revision: number;
  approved_version: number | null;
  updated_at: string;
}

export interface JobListResponse {
  items: JobSummary[];
  limit: number;
  offset: number;
}

export interface SuggestedScreeningQuestion {
  key: string;
  prompt: string;
  answer_type: ScreeningAnswerType;
  required: boolean;
  options: string[];
}

export interface JobAnalysisProposal {
  suggested_title: string | null;
  requirements: JobRequirements;
  suggested_screening_questions: SuggestedScreeningQuestion[];
}

export const emptyRequirements: JobRequirements = {
  alternate_titles: [],
  required_skills: [],
  preferred_skills: [],
  locations: [],
  min_years_experience: null,
  seniority: [],
  employment_type: null,
  work_arrangement: null,
};
