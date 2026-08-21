import Link from "next/link";

import { formatDateTime, formatMinorMoney } from "@/lib/intl";
import type { TalentSearchItem } from "@/lib/marketplace/types";

function initials(title: string): string {
  return title
    .split(/\s+/)
    .filter(Boolean)
    .slice(0, 2)
    .map((part) => part[0]?.toUpperCase() ?? "")
    .join("") || "FP";
}

export function TalentCard({ item }: { item: TalentSearchItem }) {
  const rate = item.hourly_rate_minor !== null && item.currency
    ? `${formatMinorMoney(item.hourly_rate_minor, item.currency)} / hour`
    : "Rate not published";

  return (
    <article className="talent-card">
      <div className="talent-card-topline">
        <div className="talent-avatar" aria-hidden="true">{initials(item.title)}</div>
        <div className="talent-card-identity">
          <h2><Link href={`/talent/${item.freelancer_id}`}>{item.title}</Link></h2>
          <div className="talent-meta-row">
            <span className={item.availability ? "availability-live" : "availability-away"}>
              <span aria-hidden="true" />{item.availability ? "Accepting work" : "Unavailable"}
            </span>
            <span>{item.rating === null ? "New profile" : `${item.rating.toFixed(1)} rating`}</span>
            <span>{item.completed_jobs} completed {item.completed_jobs === 1 ? "job" : "jobs"}</span>
          </div>
        </div>
        <strong className="talent-rate">{rate}</strong>
      </div>

      <p className="talent-bio">{item.bio || "This freelancer has not added a public bio yet."}</p>

      <div className="talent-skill-row" aria-label="Skills">
        {item.skills.slice(0, 8).map((skill) => <span key={skill}>{skill}</span>)}
        {item.skills.length > 8 ? <span>+{item.skills.length - 8}</span> : null}
      </div>

      <div className="talent-card-footer">
        <div>
          <span>{item.languages.length ? item.languages.join(" · ") : "Languages not published"}</span>
          <small>Search projection updated {formatDateTime(item.updated_at)}</small>
        </div>
        <Link className="talent-view-link" href={`/talent/${item.freelancer_id}`}>
          View full profile <span aria-hidden="true">↗</span>
        </Link>
      </div>
    </article>
  );
}
