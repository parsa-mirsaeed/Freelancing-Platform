"use client";

import { useState, type FormEvent } from "react";

import { ProductApiError, productJson } from "@/features/profile/profile-api";
import type { FreelancerProfile } from "@/lib/api/marketplace";
import { majorMoneyInputToMinor, minorMoneyInputValue } from "@/lib/intl";

import styles from "./profile-workspace.module.css";

function csv(value: string): string[] {
  return [...new Set(value.split(",").map((item) => item.trim()).filter(Boolean))];
}

export function ProfileForm({ profile, onSaved }: { profile: FreelancerProfile | null; onSaved: (profile: FreelancerProfile) => void }) {
  const initialCurrency = profile?.currency ?? "USD";
  const initialRate = profile?.hourly_rate_minor != null && profile.currency
    ? minorMoneyInputValue(profile.hourly_rate_minor, profile.currency)
    : "";
  const [title, setTitle] = useState(profile?.title ?? "");
  const [bio, setBio] = useState(profile?.bio ?? "");
  const [currency, setCurrency] = useState(initialCurrency);
  const [rate, setRate] = useState(initialRate);
  const [timezone, setTimezone] = useState(profile?.timezone ?? Intl.DateTimeFormat().resolvedOptions().timeZone ?? "UTC");
  const [skills, setSkills] = useState(profile?.skills.join(", ") ?? "");
  const [languages, setLanguages] = useState(profile?.languages.join(", ") ?? "");
  const [acceptingWork, setAcceptingWork] = useState(profile?.accepting_work ?? true);
  const [state, setState] = useState<{ kind: "idle" | "saving" | "success" | "error"; message?: string }>({ kind: "idle" });

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setState({ kind: "saving" });
    try {
      const normalizedCurrency = currency.trim().toUpperCase();
      if (rate && !/^[A-Z]{3}$/.test(normalizedCurrency)) {
        throw new RangeError("Use a three-letter ISO currency code such as USD, EUR, or JPY.");
      }
      const hourlyRateMinor = rate ? majorMoneyInputToMinor(rate, normalizedCurrency) : null;
      const saved = await productJson<FreelancerProfile>("freelancers/me/profile", {
        method: "PUT",
        body: JSON.stringify({
          title: title.trim(),
          bio: bio.trim(),
          hourly_rate_minor: hourlyRateMinor,
          currency: hourlyRateMinor === null ? null : normalizedCurrency,
          timezone: timezone.trim() || "UTC",
          accepting_work: acceptingWork,
          languages: csv(languages),
          skills: csv(skills),
        }),
      });
      onSaved(saved);
      setState({ kind: "success", message: "Professional profile saved." });
    } catch (error) {
      const message = error instanceof ProductApiError || error instanceof RangeError
        ? error.message
        : "Profile could not be saved.";
      setState({ kind: "error", message });
    }
  }

  return (
    <form className={styles.formSection} onSubmit={submit}>
      <div className={styles.sectionTitle}><div><span>Professional identity</span><h2>Profile</h2></div><p>Public information employers use to assess fit before commercial terms are negotiated.</p></div>
      <div className={styles.fieldGrid}>
        <label className={styles.fullField}><span>Professional title</span><input value={title} onChange={(event) => setTitle(event.target.value)} required maxLength={160} placeholder="Senior product designer" /></label>
        <label className={styles.fullField}><span>Biography</span><textarea value={bio} onChange={(event) => setBio(event.target.value)} rows={6} placeholder="Describe the problems you solve, the contexts you work in, and how you collaborate." /></label>
        <label><span>Hourly rate</span><input value={rate} onChange={(event) => setRate(event.target.value)} inputMode="decimal" placeholder="125.00" aria-describedby="rate-help" /><small id="rate-help">Enter major units; the client converts safely to backend minor units.</small></label>
        <label><span>Currency</span><input value={currency} onChange={(event) => setCurrency(event.target.value.toUpperCase())} maxLength={3} pattern="[A-Za-z]{3}" placeholder="USD" /></label>
        <label><span>Timezone</span><input value={timezone} onChange={(event) => setTimezone(event.target.value)} maxLength={64} placeholder="Europe/Zurich" /></label>
        <label className={styles.switchField}><span>Work status</span><span className={styles.switchRow}><input type="checkbox" checked={acceptingWork} onChange={(event) => setAcceptingWork(event.target.checked)} /> Accepting new work</span></label>
        <label className={styles.fullField}><span>Skills</span><input value={skills} onChange={(event) => setSkills(event.target.value)} placeholder="Product design, Design systems, Research" /><small>Comma-separated, maximum 50 skills.</small></label>
        <label className={styles.fullField}><span>Languages</span><input value={languages} onChange={(event) => setLanguages(event.target.value)} placeholder="English, German" /><small>Comma-separated, maximum 20 entries.</small></label>
      </div>
      <div className={styles.formActions}><button type="submit" disabled={state.kind === "saving"}>{state.kind === "saving" ? "Saving…" : "Save profile"}</button><p className={state.kind === "error" ? styles.errorText : styles.successText} role="status">{state.message}</p></div>
    </form>
  );
}
