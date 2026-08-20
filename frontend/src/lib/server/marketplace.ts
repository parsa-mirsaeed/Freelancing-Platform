import "server-only";

import { notFound } from "next/navigation";

import type {
  FreelancerProfile,
  FreelancerReview,
  PortfolioItem,
  TalentSearchFilters,
  TalentSearchItem,
} from "@/lib/api/marketplace";
import { talentSearchPath } from "@/lib/api/marketplace";
import { backendFetch } from "@/lib/server/backend";

export class MarketplaceReadError extends Error {
  constructor(
    public readonly status: number,
    message: string,
  ) {
    super(message);
    this.name = "MarketplaceReadError";
  }
}

async function readJson<T>(path: string): Promise<T> {
  const response = await backendFetch(path);
  if (!response.ok) {
    const body = (await response.json().catch(() => null)) as
      | { error?: { message?: string }; message?: string }
      | null;
    throw new MarketplaceReadError(
      response.status,
      body?.error?.message ?? body?.message ?? `Backend request failed with ${response.status}`,
    );
  }
  return (await response.json()) as T;
}

export async function searchTalent(filters: TalentSearchFilters): Promise<TalentSearchItem[]> {
  const payload = await readJson<{ items: TalentSearchItem[] }>(talentSearchPath(filters));
  return payload.items;
}

export async function readPublicFreelancer(userId: string): Promise<FreelancerProfile> {
  try {
    return await readJson<FreelancerProfile>(`/api/v1/freelancers/${encodeURIComponent(userId)}`);
  } catch (error) {
    if (error instanceof MarketplaceReadError && error.status === 404) notFound();
    throw error;
  }
}

export async function readPublicPortfolio(userId: string): Promise<PortfolioItem[]> {
  const payload = await readJson<{ items: PortfolioItem[] }>(
    `/api/v1/freelancers/${encodeURIComponent(userId)}/portfolio`,
  );
  return payload.items;
}

export async function readPublicReviews(userId: string): Promise<FreelancerReview[]> {
  const payload = await readJson<{ items: FreelancerReview[] }>(
    `/api/v1/freelancers/${encodeURIComponent(userId)}/reviews`,
  );
  return payload.items;
}
