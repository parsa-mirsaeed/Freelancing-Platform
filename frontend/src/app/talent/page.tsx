import type { Metadata } from "next";

import { TalentCard } from "@/components/talent/talent-card";
import { TalentSearchForm } from "@/components/talent/talent-search-form";
import { buildTalentSearchPath, parseTalentSearchParams } from "@/lib/marketplace/search";
import type { ListResponse, TalentSearchItem } from "@/lib/marketplace/types";
import { backendFetch } from "@/lib/server/backend";

export const metadata: Metadata = {
  title: "Find talent",
  description: "Search freelancer expertise, availability, ratings, and professional profiles.",
};

type PageProps = {
  searchParams: Promise<Record<string, string | string[] | undefined>>;
};

export default async function TalentPage({ searchParams }: PageProps) {
  const state = parseTalentSearchParams(await searchParams);
  let items: TalentSearchItem[] = [];
  let unavailable = false;

  try {
    const response = await backendFetch(buildTalentSearchPath(state));
    if (response.ok) {
      const payload = (await response.json()) as ListResponse<TalentSearchItem>;
      items = Array.isArray(payload.items) ? payload.items : [];
    } else {
      unavailable = true;
    }
  } catch {
    unavailable = true;
  }

  return (
    <main className="marketplace-page talent-page">
      <section className="talent-hero">
        <div className="talent-hero-copy">
          <h1>Find the right expertise without losing the signal.</h1>
          <p>
            Search the marketplace projection by professional focus, canonical skills, and current
            availability. Rankings come from the backend search index; the interface does not invent
            extra profile claims.
          </p>
        </div>
        <div className="talent-hero-note" aria-label="Search result information">
          <strong>{unavailable ? "Search unavailable" : `${items.length} ${items.length === 1 ? "result" : "results"}`}</strong>
          <span>Up to {state.limit} ranked profiles</span>
        </div>
      </section>

      <TalentSearchForm initial={state} />

      {unavailable ? (
        <section className="talent-state-panel" role="status">
          <h2>Talent search is temporarily unavailable.</h2>
          <p>The search projection could not be reached. Profile data remains authoritative in PostgreSQL; retry when Elasticsearch is healthy.</p>
        </section>
      ) : items.length === 0 ? (
        <section className="talent-state-panel">
          <h2>No profiles matched these filters.</h2>
          <p>Try a broader skill term, clear the availability filter, or search by professional title.</p>
        </section>
      ) : (
        <section className="talent-results" aria-label="Freelancer search results">
          {items.map((item) => <TalentCard key={item.freelancer_id} item={item} />)}
        </section>
      )}
    </main>
  );
}
