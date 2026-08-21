import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";

import { formatDateTime, formatMinorMoney } from "@/lib/intl";
import type {
  FreelancerProfile,
  ListResponse,
  PortfolioItem,
  Review,
} from "@/lib/marketplace/types";
import { backendFetch } from "@/lib/server/backend";

export const metadata: Metadata = {
  title: "Freelancer profile",
};

const WEEKDAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"];

type PageProps = { params: Promise<{ userId: string }> };

async function readJson<T>(response: Response): Promise<T | null> {
  if (!response.ok) return null;
  return (await response.json()) as T;
}

function averageRating(reviews: Review[]): string | null {
  if (!reviews.length) return null;
  const average = reviews.reduce((total, review) => total + review.rating, 0) / reviews.length;
  return average.toFixed(1);
}

export default async function PublicTalentProfile({ params }: PageProps) {
  const { userId } = await params;
  const [profileResponse, portfolioResponse, reviewsResponse] = await Promise.all([
    backendFetch(`/api/v1/freelancers/${encodeURIComponent(userId)}`),
    backendFetch(`/api/v1/freelancers/${encodeURIComponent(userId)}/portfolio`),
    backendFetch(`/api/v1/freelancers/${encodeURIComponent(userId)}/reviews`),
  ]);

  if (profileResponse.status === 404) notFound();
  const profile = await readJson<FreelancerProfile>(profileResponse);
  if (!profile) throw new Error("Freelancer profile could not be loaded.");

  const portfolio = (await readJson<ListResponse<PortfolioItem>>(portfolioResponse))?.items ?? [];
  const reviews = (await readJson<ListResponse<Review>>(reviewsResponse))?.items ?? [];
  const rating = averageRating(reviews);
  const rate = profile.hourly_rate_minor !== null && profile.currency
    ? `${formatMinorMoney(profile.hourly_rate_minor, profile.currency)} / hour`
    : "Rate not published";

  return (
    <main className="marketplace-page public-profile-page">
      <nav className="profile-breadcrumb" aria-label="Breadcrumb">
        <Link href="/talent">Talent</Link><span aria-hidden="true">/</span><span>Profile</span>
      </nav>

      <section className="profile-identity-grid">
        <div className="profile-identity-main">
          <div className="profile-monogram" aria-hidden="true">
            {profile.title.split(/\s+/).slice(0, 2).map((part) => part[0]?.toUpperCase()).join("")}
          </div>
          <div>
            <div className="profile-status-line">
              <span className={profile.accepting_work ? "availability-live" : "availability-away"}>
                <span aria-hidden="true" />{profile.accepting_work ? "Accepting work" : "Not accepting work"}
              </span>
              <span>{profile.timezone}</span>
            </div>
            <h1>{profile.title}</h1>
            <p>{profile.bio || "This freelancer has not added a public bio yet."}</p>
          </div>
        </div>
        <aside className="profile-commercial" aria-label="Profile summary">
          <strong>{rate}</strong>
          <div><span>Reviews</span><b>{rating ? `${rating} / 5` : "No reviews yet"}</b></div>
          <div><span>Languages</span><b>{profile.languages.length || "—"}</b></div>
          <small>Profile projection version {profile.projection_version}</small>
        </aside>
      </section>

      <section className="profile-section profile-skills-section">
        <div className="profile-section-heading"><h2>Expertise</h2><p>Canonical skills published on this profile.</p></div>
        <div className="profile-chip-rail">
          {profile.skills.length ? profile.skills.map((skill) => <span key={skill}>{skill}</span>) : <em>No skills published.</em>}
        </div>
        {profile.languages.length ? <p className="profile-languages"><strong>Languages:</strong> {profile.languages.join(" · ")}</p> : null}
      </section>

      <section className="profile-section">
        <div className="profile-section-heading"><h2>Availability</h2><p>Recurring schedule plus date-specific exceptions.</p></div>
        <div className="availability-table" role="list">
          {profile.availability.rules.length ? profile.availability.rules.map((rule, index) => (
            <div key={rule.id ?? `${rule.weekday}-${index}`} role="listitem">
              <strong>{WEEKDAYS[rule.weekday] ?? `Day ${rule.weekday}`}</strong>
              <span>{rule.start_time}–{rule.end_time}</span>
              <small>{rule.timezone}</small>
            </div>
          )) : <p className="profile-empty-copy">No recurring hours published.</p>}
        </div>
        {profile.availability.exceptions.length ? (
          <div className="availability-exceptions">
            {profile.availability.exceptions.map((exception) => (
              <article key={exception.id ?? exception.date}>
                <strong>{exception.date}</strong>
                <span>{exception.available ? (exception.start_time && exception.end_time ? `${exception.start_time}–${exception.end_time}` : "Available") : "Unavailable"}</span>
                {exception.reason ? <small>{exception.reason}</small> : null}
              </article>
            ))}
          </div>
        ) : null}
      </section>

      <section className="profile-section">
        <div className="profile-section-heading"><h2>Portfolio</h2><p>Published work samples. File metadata is shown only for backend-confirmed SAFE files.</p></div>
        {portfolio.length ? (
          <div className="portfolio-grid">
            {portfolio.map((item) => (
              <article key={item.id}>
                <div className="portfolio-index" aria-hidden="true">{String(portfolio.indexOf(item) + 1).padStart(2, "0")}</div>
                <h3>{item.title}</h3>
                <p>{item.description || "No description provided."}</p>
                <div className="portfolio-meta">
                  {item.files.length ? <span>{item.files.length} safe {item.files.length === 1 ? "file" : "files"}</span> : <span>No attached files</span>}
                  {item.external_url ? <a href={item.external_url} target="_blank" rel="noreferrer">Visit project ↗</a> : null}
                </div>
              </article>
            ))}
          </div>
        ) : <p className="profile-empty-copy">No portfolio items published yet.</p>}
      </section>

      <section className="profile-section reviews-section">
        <div className="profile-section-heading"><h2>Client reviews</h2><p>Reviews recorded after eligible completed marketplace work.</p></div>
        {reviews.length ? (
          <div className="review-list">
            {reviews.map((review) => (
              <article key={review.id}>
                <div><strong>{review.rating} / 5</strong><time dateTime={review.created_at}>{formatDateTime(review.created_at)}</time></div>
                <p>{review.comment || "No written comment."}</p>
                <small>Project {review.project_id.slice(0, 8)}</small>
              </article>
            ))}
          </div>
        ) : <p className="profile-empty-copy">No reviews yet.</p>}
      </section>
    </main>
  );
}
