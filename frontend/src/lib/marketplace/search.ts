export interface TalentSearchState {
  query: string;
  skills: string[];
  available: boolean | null;
  limit: number;
}

function first(value: string | string[] | undefined): string | undefined {
  return Array.isArray(value) ? value[0] : value;
}

function many(value: string | string[] | undefined): string[] {
  const values = Array.isArray(value) ? value : value ? [value] : [];
  return values.map((item) => item.trim()).filter(Boolean).slice(0, 20);
}

export function parseTalentSearchParams(
  params: Record<string, string | string[] | undefined>,
): TalentSearchState {
  const rawLimit = Number.parseInt(first(params.limit) ?? "20", 10);
  const available = first(params.available);
  return {
    query: (first(params.q) ?? "").trim().slice(0, 160),
    skills: many(params.skill),
    available: available === "true" ? true : available === "false" ? false : null,
    limit: Number.isFinite(rawLimit) ? Math.min(50, Math.max(1, rawLimit)) : 20,
  };
}

export function buildTalentSearchPath(state: TalentSearchState): string {
  const query = new URLSearchParams();
  if (state.query) query.set("q", state.query);
  for (const skill of state.skills) query.append("skill", skill);
  if (state.available !== null) query.set("available", String(state.available));
  query.set("limit", String(state.limit));
  return `/api/v1/search/freelancers?${query.toString()}`;
}

export function splitSkillInput(value: string): string[] {
  return [...new Set(value.split(",").map((item) => item.trim()).filter(Boolean))].slice(0, 20);
}
