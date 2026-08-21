"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useMemo, useState, type FormEvent } from "react";

import { useSession } from "@/components/providers/session-provider";
import { BrowserApiError, browserApi } from "@/lib/api/browser";
import { majorMoneyToMinor, minorMoneyToMajor } from "@/lib/marketplace/money-input";
import type {
  AvailabilityException,
  AvailabilityRule,
  FreelancerProfile,
  ListResponse,
  PortfolioItem,
} from "@/lib/marketplace/types";

const WEEKDAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"];

type LoadState = "loading" | "ready" | "error";
type Notice = { kind: "success" | "error"; message: string } | null;

function listInput(value: string): string[] {
  return [...new Set(value.split(",").map((item) => item.trim()).filter(Boolean))];
}

function blankRule(timezone: string): AvailabilityRule {
  return {
    weekday: 0,
    start_time: "09:00",
    end_time: "17:00",
    timezone: timezone || "UTC",
  };
}

function errorMessage(error: unknown, fallback: string): string {
  return error instanceof Error ? error.message : fallback;
}

export function ProfileEditor() {
  const { user, status } = useSession();
  const router = useRouter();
  const [loadState, setLoadState] = useState<LoadState>("loading");
  const [notice, setNotice] = useState<Notice>(null);
  const [saving, setSaving] = useState<string | null>(null);
  const [profileExists, setProfileExists] = useState(false);

  const [title, setTitle] = useState("");
  const [bio, setBio] = useState("");
  const [rate, setRate] = useState("");
  const [currency, setCurrency] = useState("");
  const [timezone, setTimezone] = useState("UTC");
  const [acceptingWork, setAcceptingWork] = useState(true);
  const [skills, setSkills] = useState("");
  const [languages, setLanguages] = useState("");
  const [rules, setRules] = useState<AvailabilityRule[]>([]);
  const [exceptions, setExceptions] = useState<AvailabilityException[]>([]);
  const [portfolio, setPortfolio] = useState<PortfolioItem[]>([]);

  const [exceptionDate, setExceptionDate] = useState("");
  const [exceptionAvailable, setExceptionAvailable] = useState(false);
  const [exceptionStart, setExceptionStart] = useState("");
  const [exceptionEnd, setExceptionEnd] = useState("");
  const [exceptionReason, setExceptionReason] = useState("");

  const [portfolioTitle, setPortfolioTitle] = useState("");
  const [portfolioDescription, setPortfolioDescription] = useState("");
  const [portfolioUrl, setPortfolioUrl] = useState("");

  const isFreelancer = Boolean(user?.roles.includes("freelancer"));
  const previewHref = user ? `/talent/${user.id}` : "/talent";
  const profileCompletion = useMemo(() => {
    const checks = [title, bio, skills, languages, profileExists ? "saved" : ""];
    return Math.round((checks.filter((value) => value.trim()).length / checks.length) * 100);
  }, [bio, languages, profileExists, skills, title]);

  useEffect(() => {
    if (status === "anonymous") router.replace("/login?next=/dashboard/profile");
  }, [router, status]);

  useEffect(() => {
    if (!user || status !== "authenticated" || !user.roles.includes("freelancer")) return;

    const controller = new AbortController();
    void (async () => {
      try {
        let profile: FreelancerProfile | null = null;
        try {
          profile = await browserApi<FreelancerProfile>("freelancers/me/profile", {
            signal: controller.signal,
          });
        } catch (error) {
          if (!(error instanceof BrowserApiError) || error.status !== 404) throw error;
        }

        let portfolioItems: PortfolioItem[] = [];
        if (profile) {
          const response = await browserApi<ListResponse<PortfolioItem>>(
            `freelancers/${user.id}/portfolio`,
            { signal: controller.signal },
          );
          portfolioItems = response.items ?? [];

          setProfileExists(true);
          setTitle(profile.title);
          setBio(profile.bio);
          setRate(minorMoneyToMajor(profile.hourly_rate_minor, profile.currency));
          setCurrency(profile.currency ?? "");
          setTimezone(profile.timezone);
          setAcceptingWork(profile.accepting_work);
          setSkills(profile.skills.join(", "));
          setLanguages(profile.languages.join(", "));
          setRules(profile.availability.rules);
          setExceptions(profile.availability.exceptions);
        }
        setPortfolio(portfolioItems);
        setLoadState("ready");
      } catch (error) {
        if (error instanceof DOMException && error.name === "AbortError") return;
        setNotice({ kind: "error", message: errorMessage(error, "Profile data could not be loaded.") });
        setLoadState("error");
      }
    })();
    return () => controller.abort();
  }, [status, user]);

  async function saveProfile(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setSaving("profile");
    setNotice(null);
    try {
      const normalizedCurrency = currency.trim().toUpperCase();
      if (rate.trim() && !normalizedCurrency) {
        throw new Error("Choose a currency when publishing a rate.");
      }
      const hourlyRateMinor = rate.trim() ? majorMoneyToMinor(rate, normalizedCurrency) : null;
      const publishedCurrency = hourlyRateMinor === null ? null : normalizedCurrency;
      const saved = await browserApi<FreelancerProfile>("freelancers/me/profile", {
        method: "PUT",
        body: JSON.stringify({
          title: title.trim(),
          bio: bio.trim(),
          hourly_rate_minor: hourlyRateMinor,
          currency: publishedCurrency,
          timezone: timezone.trim() || "UTC",
          accepting_work: acceptingWork,
          languages: listInput(languages),
          skills: listInput(skills),
        }),
      });
      setProfileExists(true);
      setCurrency(saved.currency ?? "");
      setRate(minorMoneyToMajor(saved.hourly_rate_minor, saved.currency));
      setNotice({ kind: "success", message: "Professional profile saved." });
    } catch (error) {
      setNotice({ kind: "error", message: errorMessage(error, "Profile could not be saved.") });
    } finally {
      setSaving(null);
    }
  }

  async function saveRules() {
    if (!profileExists) return;
    setSaving("rules");
    setNotice(null);
    try {
      const payload = rules.map(({ weekday, start_time, end_time, timezone: ruleTimezone }) => ({
        weekday,
        start_time,
        end_time,
        timezone: ruleTimezone.trim() || timezone.trim() || "UTC",
      }));
      const response = await browserApi<{ rules: AvailabilityRule[] }>(
        "freelancers/me/availability/rules",
        { method: "PUT", body: JSON.stringify({ rules: payload }) },
      );
      setRules(response.rules);
      setNotice({ kind: "success", message: "Recurring availability saved." });
    } catch (error) {
      setNotice({ kind: "error", message: errorMessage(error, "Availability could not be saved.") });
    } finally {
      setSaving(null);
    }
  }

  async function saveException(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!profileExists) return;
    setSaving("exception");
    setNotice(null);
    try {
      const saved = await browserApi<AvailabilityException>(
        "freelancers/me/availability/exceptions",
        {
          method: "PUT",
          body: JSON.stringify({
            date: exceptionDate,
            available: exceptionAvailable,
            start_time: exceptionAvailable && exceptionStart ? exceptionStart : null,
            end_time: exceptionAvailable && exceptionEnd ? exceptionEnd : null,
            reason: exceptionReason.trim() || null,
          }),
        },
      );
      setExceptions((current) =>
        [...current.filter((item) => item.date !== saved.date), saved].sort((a, b) =>
          a.date.localeCompare(b.date),
        ),
      );
      setExceptionDate("");
      setExceptionReason("");
      setExceptionStart("");
      setExceptionEnd("");
      setNotice({ kind: "success", message: "Availability exception saved." });
    } catch (error) {
      setNotice({ kind: "error", message: errorMessage(error, "Exception could not be saved.") });
    } finally {
      setSaving(null);
    }
  }

  async function addPortfolio(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!profileExists) return;
    setSaving("portfolio");
    setNotice(null);
    try {
      const item = await browserApi<PortfolioItem>("freelancers/me/portfolio", {
        method: "POST",
        body: JSON.stringify({
          title: portfolioTitle.trim(),
          description: portfolioDescription.trim(),
          external_url: portfolioUrl.trim() || null,
        }),
      });
      setPortfolio((current) => [item, ...current]);
      setPortfolioTitle("");
      setPortfolioDescription("");
      setPortfolioUrl("");
      setNotice({ kind: "success", message: "Portfolio item added." });
    } catch (error) {
      setNotice({ kind: "error", message: errorMessage(error, "Portfolio item could not be added.") });
    } finally {
      setSaving(null);
    }
  }

  async function removePortfolio(itemId: string) {
    setSaving(`portfolio-${itemId}`);
    setNotice(null);
    try {
      await browserApi<void>(`portfolio/${itemId}`, { method: "DELETE" });
      setPortfolio((current) => current.filter((item) => item.id !== itemId));
      setNotice({ kind: "success", message: "Portfolio item removed." });
    } catch (error) {
      setNotice({ kind: "error", message: errorMessage(error, "Portfolio item could not be removed.") });
    } finally {
      setSaving(null);
    }
  }

  if (status === "loading") {
    return <main className="profile-studio"><div className="studio-loading" role="status">Opening profile studio…</div></main>;
  }
  if (!user) return null;
  if (!isFreelancer) {
    return (
      <main className="profile-studio">
        <section className="studio-role-state">
          <h1>Freelancer profile studio</h1>
          <p>This workspace is available to freelancer accounts. Employer discovery lives in the public talent marketplace.</p>
          <Link href="/talent">Browse talent</Link>
        </section>
      </main>
    );
  }
  if (loadState === "loading") {
    return <main className="profile-studio"><div className="studio-loading" role="status">Loading profile studio…</div></main>;
  }

  return (
    <main className="profile-studio">
      <header className="studio-header">
        <div>
          <p className="studio-context">Freelancer workspace</p>
          <h1>Professional profile</h1>
          <p>Manage the public data employers use to evaluate expertise and availability.</p>
        </div>
        <div className="studio-header-actions">
          <div className="studio-completion"><span>Profile signal</span><strong>{profileCompletion}%</strong></div>
          <Link href={previewHref}>View public profile ↗</Link>
        </div>
      </header>

      {notice ? <div className={`studio-notice studio-notice-${notice.kind}`} role="status">{notice.message}</div> : null}
      {loadState === "error" ? <div className="studio-notice studio-notice-error">Reload the page to retry profile loading.</div> : null}

      <div className="studio-layout">
        <div className="studio-main-column">
          <form className="studio-panel" onSubmit={saveProfile}>
            <div className="studio-panel-heading">
              <div><span>01</span><h2>Professional identity</h2></div>
              <p>Title, narrative, skills, languages, and rate are published directly from the freelancer profile API.</p>
            </div>
            <div className="studio-field-grid">
              <label className="studio-field studio-field-wide">
                <span>Professional title</span>
                <input required maxLength={160} value={title} onChange={(event) => setTitle(event.target.value)} placeholder="Senior product designer" />
              </label>
              <label className="studio-field studio-field-wide">
                <span>Bio</span>
                <textarea rows={6} value={bio} onChange={(event) => setBio(event.target.value)} placeholder="Describe the work you do, the problems you solve, and the context you work best in." />
              </label>
              <label className="studio-field studio-field-wide">
                <span>Skills</span>
                <input required value={skills} onChange={(event) => setSkills(event.target.value)} placeholder="Python, FastAPI, PostgreSQL" />
                <small>Comma-separated; the backend canonicalizes skill identities.</small>
              </label>
              <label className="studio-field studio-field-wide">
                <span>Languages</span>
                <input value={languages} onChange={(event) => setLanguages(event.target.value)} placeholder="English, German" />
              </label>
              <label className="studio-field">
                <span>Hourly rate</span>
                <input inputMode="decimal" value={rate} onChange={(event) => setRate(event.target.value)} placeholder="120" />
              </label>
              <label className="studio-field">
                <span>Currency</span>
                <input value={currency} onChange={(event) => setCurrency(event.target.value.toUpperCase().slice(0, 3))} placeholder="USD" minLength={3} maxLength={3} />
              </label>
              <label className="studio-field">
                <span>IANA timezone</span>
                <input required value={timezone} onChange={(event) => setTimezone(event.target.value)} placeholder="Europe/Zurich" />
              </label>
              <label className="studio-toggle">
                <input type="checkbox" checked={acceptingWork} onChange={(event) => setAcceptingWork(event.target.checked)} />
                <span><strong>Accepting new work</strong><small>This becomes the public availability filter signal.</small></span>
              </label>
            </div>
            <div className="studio-panel-actions">
              <button type="submit" disabled={saving === "profile"}>{saving === "profile" ? "Saving…" : profileExists ? "Save profile" : "Publish profile"}</button>
            </div>
          </form>

          <section className="studio-panel">
            <div className="studio-panel-heading">
              <div><span>02</span><h2>Recurring availability</h2></div>
              <p>Multiple time windows per weekday are preserved; nothing is collapsed into a single schedule row.</p>
            </div>
            {!profileExists ? <p className="studio-empty">Publish your professional identity before adding availability.</p> : null}
            <div className="schedule-editor">
              {rules.map((rule, index) => (
                <div className="schedule-row" key={rule.id ?? `new-${index}`}>
                  <label>
                    <span>Day</span>
                    <select value={rule.weekday} onChange={(event) => setRules((current) => current.map((item, itemIndex) => itemIndex === index ? { ...item, weekday: Number(event.target.value) } : item))}>
                      {WEEKDAYS.map((day, dayIndex) => <option key={day} value={dayIndex}>{day}</option>)}
                    </select>
                  </label>
                  <label><span>Start</span><input type="time" value={rule.start_time} onChange={(event) => setRules((current) => current.map((item, itemIndex) => itemIndex === index ? { ...item, start_time: event.target.value } : item))} /></label>
                  <label><span>End</span><input type="time" value={rule.end_time} onChange={(event) => setRules((current) => current.map((item, itemIndex) => itemIndex === index ? { ...item, end_time: event.target.value } : item))} /></label>
                  <label><span>Timezone</span><input value={rule.timezone} onChange={(event) => setRules((current) => current.map((item, itemIndex) => itemIndex === index ? { ...item, timezone: event.target.value } : item))} /></label>
                  <button className="schedule-remove" type="button" onClick={() => setRules((current) => current.filter((_, itemIndex) => itemIndex !== index))}>Remove</button>
                </div>
              ))}
              <button className="studio-secondary-button" type="button" disabled={!profileExists} onClick={() => setRules((current) => [...current, blankRule(timezone)])}>+ Add time window</button>
            </div>
            <div className="studio-panel-actions">
              <button type="button" onClick={() => void saveRules()} disabled={!profileExists || saving === "rules"}>{saving === "rules" ? "Saving…" : "Save recurring hours"}</button>
            </div>
          </section>

          <section className="studio-panel">
            <div className="studio-panel-heading">
              <div><span>03</span><h2>Date exceptions</h2></div>
              <p>Exceptions are upserted by date because the current backend exposes update/create semantics but no delete endpoint.</p>
            </div>
            {!profileExists ? (
              <p className="studio-empty">Publish your professional identity before adding exceptions.</p>
            ) : exceptions.length ? (
              <div className="exception-list">
                {exceptions.map((item) => (
                  <div key={item.id ?? item.date}>
                    <strong>{item.date}</strong>
                    <span>{item.available ? item.start_time && item.end_time ? `${item.start_time}–${item.end_time}` : "Available" : "Unavailable"}</span>
                    <small>{item.reason || "No reason"}</small>
                  </div>
                ))}
              </div>
            ) : <p className="studio-empty">No date exceptions yet.</p>}
            <form className="exception-form" onSubmit={saveException}>
              <label><span>Date</span><input required type="date" value={exceptionDate} disabled={!profileExists} onChange={(event) => setExceptionDate(event.target.value)} /></label>
              <label className="studio-toggle compact"><input type="checkbox" checked={exceptionAvailable} disabled={!profileExists} onChange={(event) => setExceptionAvailable(event.target.checked)} /><span><strong>Available that day</strong></span></label>
              <label><span>Start</span><input type="time" disabled={!profileExists || !exceptionAvailable} value={exceptionStart} onChange={(event) => setExceptionStart(event.target.value)} /></label>
              <label><span>End</span><input type="time" disabled={!profileExists || !exceptionAvailable} value={exceptionEnd} onChange={(event) => setExceptionEnd(event.target.value)} /></label>
              <label className="exception-reason"><span>Reason</span><input maxLength={240} value={exceptionReason} disabled={!profileExists} onChange={(event) => setExceptionReason(event.target.value)} placeholder="Conference, holiday, focused project day…" /></label>
              <button type="submit" disabled={!profileExists || saving === "exception"}>{saving === "exception" ? "Saving…" : "Save exception"}</button>
            </form>
          </section>
        </div>

        <aside className="studio-side-column">
          <section className="studio-panel portfolio-studio-panel">
            <div className="studio-panel-heading compact">
              <div><span>04</span><h2>Portfolio</h2></div>
              <p>Text work samples now; safe file uploads are connected in the communication/files PR.</p>
            </div>
            {!profileExists ? <p className="studio-empty">Publish your professional identity before adding portfolio work.</p> : null}
            <form className="portfolio-create-form" onSubmit={addPortfolio}>
              <label><span>Title</span><input required maxLength={160} value={portfolioTitle} disabled={!profileExists} onChange={(event) => setPortfolioTitle(event.target.value)} /></label>
              <label><span>Description</span><textarea rows={4} value={portfolioDescription} disabled={!profileExists} onChange={(event) => setPortfolioDescription(event.target.value)} /></label>
              <label><span>External URL</span><input type="url" value={portfolioUrl} disabled={!profileExists} onChange={(event) => setPortfolioUrl(event.target.value)} placeholder="https://…" /></label>
              <button type="submit" disabled={!profileExists || saving === "portfolio"}>{saving === "portfolio" ? "Adding…" : "Add portfolio item"}</button>
            </form>
            <div className="portfolio-editor-list">
              {portfolio.map((item) => (
                <article key={item.id}>
                  <div><strong>{item.title}</strong><span>{item.files.length ? `${item.files.length} safe file${item.files.length === 1 ? "" : "s"}` : "No files"}</span></div>
                  <p>{item.description || "No description."}</p>
                  <div className="portfolio-editor-actions">
                    {item.external_url ? <a href={item.external_url} target="_blank" rel="noreferrer">Open ↗</a> : <span />}
                    <button type="button" disabled={saving === `portfolio-${item.id}`} onClick={() => void removePortfolio(item.id)}>{saving === `portfolio-${item.id}` ? "Removing…" : "Remove"}</button>
                  </div>
                </article>
              ))}
              {!portfolio.length && profileExists ? <p className="studio-empty">No portfolio items yet.</p> : null}
            </div>
          </section>
        </aside>
      </div>
    </main>
  );
}
