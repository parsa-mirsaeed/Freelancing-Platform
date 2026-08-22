import type { Metadata } from "next";
import Link from "next/link";

import { normalizeSkillFilters } from "@/lib/api/marketplace";
import { formatMinorMoney } from "@/lib/intl";
import { MarketplaceReadError, searchTalent } from "@/lib/server/marketplace";

import styles from "./talent.module.css";

export const metadata: Metadata = {
  title: "Find talent",
  description: "Search professional freelancer profiles by expertise and availability.",
};

type SearchParams = Promise<Record<string, string | string[] | undefined>>;

function values(value: string | string[] | undefined): string[] {
  if (!value) return [];
  return Array.isArray(value) ? value : [value];
}

function initials(title: string): string {
  return title
    .split(/\s+/)
    .filter(Boolean)
    .slice(0, 2)
    .map((part) => part[0]?.toUpperCase() ?? "")
    .join("") || "FP";
}

export default async function TalentPage({ searchParams }: { searchParams: SearchParams }) {
  const params = await searchParams;
  const query = typeof params.q === "string" ? params.q.trim() : "";
  const skills = normalizeSkillFilters(values(params.skill));
  const available = params.available === "true" ? true : undefined;

  let items = [] as Awaited<ReturnType<typeof searchTalent>>;
  let unavailable = false;
  try {
    items = await searchTalent({ query, skills, available, limit: 24 });
  } catch (error) {
    unavailable = error instanceof MarketplaceReadError || error instanceof TypeError;
    if (!unavailable) throw error;
  }

  const hasFilters = Boolean(query || skills.length > 0 || available);

  return (
    <main className={styles.page}>
      <section className={styles.intro}>
        <div className={styles.introInner}>
          <p className={styles.overline}>Talent marketplace</p>
          <h1>Find the right expertise without losing the signal.</h1>
          <p className={styles.lede}>
            Search professional profiles by role, skill, and current availability. Results come from the
            platform&apos;s rebuildable freelancer search projection; profile details remain authoritative in PostgreSQL.
          </p>
        </div>
      </section>

      <section className={styles.workspace} aria-label="Talent search">
        <form className={styles.filters} method="get" action="/talent">
          <div className={styles.filterHeading}>
            <span>Refine search</span>
            {hasFilters ? <Link href="/talent">Reset</Link> : null}
          </div>
          <label>
            <span>What do you need?</span>
            <input name="q" defaultValue={query} placeholder="Product designer, Python, motion…" maxLength={160} />
          </label>
          <label>
            <span>Skills</span>
            <input
              name="skill"
              defaultValue={skills.join(", ")}
              placeholder="React, brand systems"
              aria-describedby="skill-help"
            />
            <small id="skill-help">Separate multiple skills with commas.</small>
          </label>
          <label className={styles.checkboxRow}>
            <input type="checkbox" name="available" value="true" defaultChecked={available === true} />
            <span>Available for work now</span>
          </label>
          <button type="submit">Search talent</button>
        </form>

        <div className={styles.results}>
          <div className={styles.resultsHeader}>
            <div>
              <span>Professionals</span>
              <strong>{unavailable ? "Search unavailable" : `${items.length} result${items.length === 1 ? "" : "s"}`}</strong>
            </div>
            {skills.length > 0 ? (
              <div className={styles.activeSkills} aria-label="Active skill filters">
                {skills.map((skill) => <span key={skill}>{skill}</span>)}
              </div>
            ) : null}
          </div>

          {unavailable ? (
            <div className={styles.statePanel} role="status">
              <strong>Talent search is temporarily unavailable.</strong>
              <p>The marketplace remains safe to use; retry when the search projection is reachable.</p>
            </div>
          ) : items.length === 0 ? (
            <div className={styles.statePanel}>
              <strong>No profiles match these filters yet.</strong>
              <p>Try a broader role description, fewer skills, or include professionals who are not currently accepting work.</p>
            </div>
          ) : (
            <div className={styles.resultList}>
              {items.map((item) => (
                <article className={styles.resultCard} key={item.freelancer_id}>
                  <div className={styles.identity}>
                    <div className={styles.avatar} aria-hidden="true">{initials(item.title)}</div>
                    <div>
                      <div className={styles.titleLine}>
                        <h2><Link href={`/talent/${item.freelancer_id}`}>{item.title}</Link></h2>
                        <span className={item.availability ? styles.available : styles.unavailable}>
                          {item.availability ? "Available" : "Unavailable"}
                        </span>
                      </div>
                      <div className={styles.proofLine}>
                        <span aria-label={item.rating === null ? "No rating yet" : `Rated ${item.rating} out of 5`}>
                          <b aria-hidden="true">★</b> {item.rating === null ? "New" : item.rating.toFixed(1)}
                        </span>
                        <span>{item.completed_jobs} completed job{item.completed_jobs === 1 ? "" : "s"}</span>
                        {item.hourly_rate_minor !== null && item.currency ? (
                          <span>{formatMinorMoney(item.hourly_rate_minor, item.currency)} / hr</span>
                        ) : null}
                      </div>
                    </div>
                  </div>
                  <p className={styles.bio}>{item.bio || "This professional has not added a public biography yet."}</p>
                  <div className={styles.cardFooter}>
                    <div className={styles.skills}>
                      {item.skills.slice(0, 6).map((skill) => <span key={skill}>{skill.replaceAll("-", " ")}</span>)}
                    </div>
                    <Link className={styles.viewLink} href={`/talent/${item.freelancer_id}`}>View profile <span aria-hidden="true">→</span></Link>
                  </div>
                </article>
              ))}
            </div>
          )}
        </div>
      </section>
    </main>
  );
}
