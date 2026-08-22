export interface AvailabilityRule {
  id: string;
  weekday: number;
  start_time: string;
  end_time: string;
  timezone: string;
}

export interface AvailabilityException {
  id: string;
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

export interface FreelancerReview {
  id: string;
  project_id: string;
  reviewer_user_id: string;
  freelancer_user_id: string;
  rating: number;
  comment: string;
  created_at: string;
}

export interface TalentSearchFilters {
  query?: string;
  skills?: string[];
  available?: boolean;
  limit?: number;
}

export function normalizeSkillFilters(values: string[]): string[] {
  const unique = new Set<string>();
  for (const value of values) {
    for (const item of value.split(",")) {
      const normalized = item.trim();
      if (normalized) unique.add(normalized);
    }
  }
  return [...unique].slice(0, 12);
}

export function talentSearchPath(filters: TalentSearchFilters): string {
  const params = new URLSearchParams();
  const query = filters.query?.trim();
  if (query) params.set("q", query);
  for (const skill of normalizeSkillFilters(filters.skills ?? [])) params.append("skill", skill);
  if (filters.available !== undefined) params.set("available", String(filters.available));
  params.set("limit", String(Math.min(Math.max(filters.limit ?? 20, 1), 50)));
  return `/api/v1/search/freelancers?${params.toString()}`;
}

export function averageReviewRating(reviews: FreelancerReview[]): number | null {
  if (reviews.length === 0) return null;
  return reviews.reduce((total, review) => total + review.rating, 0) / reviews.length;
}
