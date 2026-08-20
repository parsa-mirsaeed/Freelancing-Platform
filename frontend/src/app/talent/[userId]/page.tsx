import type { Metadata } from "next";
import Link from "next/link";

import { averageReviewRating } from "@/lib/api/marketplace";
import { formatDateTime, formatMinorMoney } from "@/lib/intl";
import {
  readPublicFreelancer,
  readPublicPortfolio,
  readPublicReviews,
} from "@/lib/server/marketplace";

import styles from "./profile.module.css";

const WEEKDAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"] as const;

type Params = Promise<{ userId: string }>;

export async function generateMetadata({ params }: { params: Params }): Promise<Metadata> {
  const { userId } = await params;
  const profile = await readPublicFreelancer(userId);
  return {
    title: profile.title,
    description: profile.bio.slice(0, 155) || `Professional freelancer profile for ${profile.title}.`,
  };
}

export default async function TalentProfilePage({ params }: { params: Params }) {
  const { userId } = await params;
  const [profile, portfolio, reviews] = await Promise.all([
    readPublicFreelancer(userId),
    readPublicPortfolio(userId),
    readPublicReviews(userId),
  ]);
  const rating = averageReviewRating(reviews);

  return (
    <main className={styles.page}>
      <section className={styles.hero}>
        <div className={styles.heroInner}>
          <Link className={styles.backLink} href="/talent">← Back to talent</Link>
          <div className={styles.heroGrid}>
            <div>
              <div className={styles.statusLine}>
                <span className={profile.accepting_work ? styles.available : styles.unavailable}>
                  {profile.accepting_work ? "Accepting work" : "Not accepting work"}
                </span>
                <span>{profile.timezone}</span>
              </div>
              <h1>{profile.title}</h1>
              <p>{profile.bio || "This professional has not added a public biography yet."}</p>
              <div className={styles.proofRow}>
                <div><strong>{rating === null ? "—" : rating.toFixed(1)}</strong><span>Average rating</span></div>
                <div><strong>{reviews.length}</strong><span>Verified review{reviews.length === 1 ? "" : "s"}</span></div>
                <div><strong>{profile.languages.length || "—"}</strong><span>Language{profile.languages.length === 1 ? "" : "s"}</span></div>
              </div>
            </div>
            <aside className={styles.ratePanel}>
              <span>Hourly rate</span>
              <strong>
                {profile.hourly_rate_minor !== null && profile.currency
                  ? formatMinorMoney(profile.hourly_rate_minor, profile.currency)
                  : "Not listed"}
              </strong>
              <p>Commercial terms are finalized through proposals and contracts; this public rate is profile guidance only.</p>
              <Link href="/register">Create an account to work together</Link>
            </aside>
          </div>
        </div>
      </section>

      <div className={styles.body}>
        <div className={styles.mainColumn}>
          <section className={styles.section}>
            <div className={styles.sectionHeading}><span>Expertise</span><h2>Skills and working languages</h2></div>
            <div className={styles.skillCloud}>
              {profile.skills.length ? profile.skills.map((skill) => <span key={skill}>{skill}</span>) : <p>No skills listed yet.</p>}
            </div>
            {profile.languages.length ? <p className={styles.languages}>Languages: {profile.languages.join(" · ")}</p> : null}
          </section>

          <section className={styles.section}>
            <div className={styles.sectionHeading}><span>Selected work</span><h2>Portfolio</h2></div>
            {portfolio.length ? (
              <div className={styles.portfolioGrid}>
                {portfolio.map((item) => (
                  <article className={styles.portfolioCard} key={item.id}>
                    <div className={styles.portfolioVisual} aria-hidden="true"><span>{item.title.slice(0, 1).toUpperCase()}</span></div>
                    <div className={styles.portfolioCopy}>
                      <div><h3>{item.title}</h3>{item.files.length ? <span>{item.files.length} safe file{item.files.length === 1 ? "" : "s"}</span> : null}</div>
                      <p>{item.description || "No project description provided."}</p>
                      {item.external_url ? <a href={item.external_url} target="_blank" rel="noreferrer">Open external work ↗</a> : null}
                    </div>
                  </article>
                ))}
              </div>
            ) : <p className={styles.emptyCopy}>No portfolio items have been published yet.</p>}
          </section>

          <section className={styles.section}>
            <div className={styles.sectionHeading}><span>Client feedback</span><h2>Reviews</h2></div>
            {reviews.length ? (
              <div className={styles.reviewList}>
                {reviews.map((review) => (
                  <article key={review.id}>
                    <div><strong aria-label={`${review.rating} out of 5 stars`}><span aria-hidden="true">{"★".repeat(review.rating)}</span></strong><time dateTime={review.created_at}>{formatDateTime(review.created_at, "en-US", profile.timezone)}</time></div>
                    <p>{review.comment || "The employer left a rating without a written comment."}</p>
                  </article>
                ))}
              </div>
            ) : <p className={styles.emptyCopy}>No reviews have been published yet.</p>}
          </section>
        </div>

        <aside className={styles.availabilityPanel}>
          <div className={styles.sectionHeading}><span>Schedule</span><h2>Typical availability</h2></div>
          {profile.availability.rules.length ? (
            <ol>
              {[...profile.availability.rules]
                .sort((a, b) => a.weekday - b.weekday || a.start_time.localeCompare(b.start_time))
                .map((rule) => (
                  <li key={rule.id}>
                    <span>{WEEKDAYS[rule.weekday] ?? `Day ${rule.weekday + 1}`}</span>
                    <strong>{rule.start_time}–{rule.end_time}</strong>
                  </li>
                ))}
            </ol>
          ) : <p className={styles.emptyCopy}>No recurring schedule is published.</p>}
          <p className={styles.timezoneNote}>Times shown in {profile.timezone}. Date-specific exceptions are reflected by the platform when work is scheduled.</p>
        </aside>
      </div>
    </main>
  );
}
