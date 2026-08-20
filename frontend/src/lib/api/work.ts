import { majorMoneyInputToMinor } from "@/lib/intl";

export type GigTier = "BASIC" | "STANDARD" | "PREMIUM";

export interface GigPackage {
  id: string;
  tier: GigTier;
  amount_minor: number;
  currency: string;
  delivery_days: number;
  revisions: number;
  description: string;
}

export interface GigRequirement {
  id: string;
  prompt: string;
  required: boolean;
}

export interface Gig {
  id: string;
  freelancer_profile_id: string;
  title: string;
  description: string;
  is_active: boolean;
  packages: GigPackage[];
  requirements: GigRequirement[];
}

export interface Project {
  id: string;
  employer_user_id: string;
  title: string;
  description: string;
  budget_min_minor: number | null;
  budget_max_minor: number | null;
  currency: string | null;
  status: "OPEN" | "CLOSED" | string;
  skills: string[];
}

export interface ProjectBudgetFields {
  budget_min_minor: number | null;
  budget_max_minor: number | null;
  currency: string | null;
}

const TIER_ORDER: Record<GigTier, number> = { BASIC: 0, STANDARD: 1, PREMIUM: 2 };

export function sortGigPackages(packages: GigPackage[]): GigPackage[] {
  return [...packages].sort((left, right) => TIER_ORDER[left.tier] - TIER_ORDER[right.tier]);
}

export function minimumGigPackage(gig: Gig): GigPackage | null {
  const packages = sortGigPackages(gig.packages);
  return packages[0] ?? null;
}

export function parseProjectBudget(
  minimum: string,
  maximum: string,
  currency: string,
): ProjectBudgetFields {
  const values = [minimum.trim(), maximum.trim(), currency.trim()];
  if (values.every((value) => value === "")) {
    return { budget_min_minor: null, budget_max_minor: null, currency: null };
  }
  if (values.some((value) => value === "")) {
    throw new RangeError("Minimum, maximum, and currency must be provided together.");
  }
  const normalizedCurrency = currency.trim().toUpperCase();
  const minMinor = majorMoneyInputToMinor(minimum, normalizedCurrency);
  const maxMinor = majorMoneyInputToMinor(maximum, normalizedCurrency);
  if (maxMinor < minMinor) throw new RangeError("Maximum budget must be at least the minimum budget.");
  return {
    budget_min_minor: minMinor,
    budget_max_minor: maxMinor,
    currency: normalizedCurrency,
  };
}

export function normalizeWorkSkills(value: string): string[] {
  return [...new Set(value.split(",").map((item) => item.trim()).filter(Boolean))].slice(0, 50);
}
