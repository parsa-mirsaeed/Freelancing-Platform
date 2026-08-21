export interface TalentSearchItem {
  freelancer_id: string;
  title: string;
  bio: string;
  skills: string[];
  rating: number | null;
  completed_jobs: number;
  hourly_rate_minor: number | null;
  currency: string | null;
  availability: boolean;
  languages: string[];
  projection_version: number;
  updated_at: string;
}

export interface AvailabilityRule {
  id?: string;
  weekday: number;
  start_time: string;
  end_time: string;
  timezone: string;
}

export interface AvailabilityException {
  id?: string;
  date: string;
  available: boolean;
  start_time: string | null;
  end_time: string | null;
  reason: string | null;
}

export interface FreelancerProfile {
  id: string;
  user_id: string;
  title: string;
  bio: string;
  hourly_rate_minor: number | null;
  currency: string | null;
  timezone: string;
  accepting_work: boolean;
  languages: string[];
  skills: string[];
  projection_version: number;
  availability: {
    rules: AvailabilityRule[];
    exceptions: AvailabilityException[];
  };
}

export interface PortfolioFile {
  id: string;
  mime_type: string;
  file_size_bytes: number;
  scan_status: "SAFE" | string;
}

export interface PortfolioItem {
  id: string;
  title: string;
  description: string;
  external_url: string | null;
  files: PortfolioFile[];
}

export interface Review {
  id: string;
  project_id: string;
  reviewer_user_id: string;
  freelancer_user_id: string;
  rating: number;
  comment: string;
  created_at: string;
}

export interface ListResponse<T> {
  items: T[];
}
