"use client";

import { useState, type FormEvent } from "react";

import { ProductApiError, productJson } from "@/features/profile/profile-api";
import type { AvailabilityException, AvailabilityRule, FreelancerProfile } from "@/lib/api/marketplace";

import styles from "./profile-workspace.module.css";

const WEEKDAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"] as const;
type EditableRule = Omit<AvailabilityRule, "id"> & { key: string };

function ruleFrom(profile: FreelancerProfile): EditableRule[] {
  return profile.availability.rules.map((rule) => ({ ...rule, key: rule.id }));
}

export function AvailabilityEditor({ profile }: { profile: FreelancerProfile }) {
  const [rules, setRules] = useState<EditableRule[]>(() => ruleFrom(profile));
  const [exceptions, setExceptions] = useState<AvailabilityException[]>(profile.availability.exceptions);
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");
  const [savingRules, setSavingRules] = useState(false);
  const [exceptionDate, setExceptionDate] = useState("");
  const [exceptionAvailable, setExceptionAvailable] = useState(false);
  const [exceptionStart, setExceptionStart] = useState("");
  const [exceptionEnd, setExceptionEnd] = useState("");
  const [exceptionReason, setExceptionReason] = useState("");

  function updateRule(key: string, patch: Partial<EditableRule>) {
    setRules((current) => current.map((rule) => rule.key === key ? { ...rule, ...patch } : rule));
  }

  async function saveRules() {
    setSavingRules(true);
    setError("");
    setMessage("");
    try {
      const payload = await productJson<{ rules: AvailabilityRule[] }>("freelancers/me/availability/rules", {
        method: "PUT",
        body: JSON.stringify({
          rules: rules.map((rule) => ({
            weekday: rule.weekday,
            start_time: rule.start_time,
            end_time: rule.end_time,
            timezone: rule.timezone,
          })),
        }),
      });
      setRules(payload.rules.map((rule) => ({ ...rule, key: rule.id })));
      setMessage("Weekly availability saved.");
    } catch (caught) {
      setError(caught instanceof ProductApiError ? caught.message : "Availability could not be saved.");
    } finally {
      setSavingRules(false);
    }
  }

  async function saveException(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError("");
    setMessage("");
    try {
      const payload = await productJson<AvailabilityException>("freelancers/me/availability/exceptions", {
        method: "PUT",
        body: JSON.stringify({
          date: exceptionDate,
          available: exceptionAvailable,
          start_time: exceptionAvailable && exceptionStart ? exceptionStart : null,
          end_time: exceptionAvailable && exceptionEnd ? exceptionEnd : null,
          reason: exceptionReason.trim() || null,
        }),
      });
      setExceptions((current) => [...current.filter((item) => item.date !== payload.date), payload].sort((a, b) => a.date.localeCompare(b.date)));
      setMessage("Date exception saved.");
      setExceptionDate("");
      setExceptionReason("");
      setExceptionStart("");
      setExceptionEnd("");
    } catch (caught) {
      setError(caught instanceof ProductApiError ? caught.message : "Date exception could not be saved.");
    }
  }

  return (
    <section className={styles.formSection}>
      <div className={styles.sectionTitle}><div><span>Calendar</span><h2>Availability</h2></div><p>Publish recurring working windows in an IANA timezone, then override specific dates when needed.</p></div>
      <div className={styles.ruleList}>
        {rules.map((rule) => (
          <div className={styles.ruleRow} key={rule.key}>
            <select aria-label="Weekday" value={rule.weekday} onChange={(event) => updateRule(rule.key, { weekday: Number(event.target.value) })}>{WEEKDAYS.map((day, index) => <option key={day} value={index}>{day}</option>)}</select>
            <input aria-label="Start time" type="time" value={rule.start_time} onChange={(event) => updateRule(rule.key, { start_time: event.target.value })} />
            <span aria-hidden="true">to</span>
            <input aria-label="End time" type="time" value={rule.end_time} onChange={(event) => updateRule(rule.key, { end_time: event.target.value })} />
            <input aria-label="Timezone" value={rule.timezone} onChange={(event) => updateRule(rule.key, { timezone: event.target.value })} />
            <button className={styles.quietButton} type="button" onClick={() => setRules((current) => current.filter((item) => item.key !== rule.key))}>Remove</button>
          </div>
        ))}
      </div>
      <div className={styles.inlineActions}>
        <button className={styles.secondaryButton} type="button" onClick={() => setRules((current) => [...current, { key: crypto.randomUUID(), weekday: 0, start_time: "09:00", end_time: "17:00", timezone: profile.timezone }])}>Add weekly window</button>
        <button type="button" disabled={savingRules} onClick={saveRules}>{savingRules ? "Saving…" : "Save weekly schedule"}</button>
      </div>

      <form className={styles.exceptionForm} onSubmit={saveException}>
        <h3>Date-specific exception</h3>
        <div className={styles.exceptionGrid}>
          <label><span>Date</span><input type="date" required value={exceptionDate} onChange={(event) => setExceptionDate(event.target.value)} /></label>
          <label className={styles.switchField}><span>Available that day</span><span className={styles.switchRow}><input type="checkbox" checked={exceptionAvailable} onChange={(event) => setExceptionAvailable(event.target.checked)} /> Available</span></label>
          <label><span>Start</span><input type="time" disabled={!exceptionAvailable} value={exceptionStart} onChange={(event) => setExceptionStart(event.target.value)} /></label>
          <label><span>End</span><input type="time" disabled={!exceptionAvailable} value={exceptionEnd} onChange={(event) => setExceptionEnd(event.target.value)} /></label>
          <label className={styles.fullField}><span>Reason</span><input maxLength={240} value={exceptionReason} onChange={(event) => setExceptionReason(event.target.value)} placeholder="Holiday, conference, limited hours…" /></label>
        </div>
        <button type="submit">Save date exception</button>
      </form>

      {exceptions.length ? <div className={styles.exceptionList}>{exceptions.slice(0, 8).map((item) => <div key={item.id}><time dateTime={item.date}>{item.date}</time><strong>{item.available ? `${item.start_time ?? "Flexible"}${item.end_time ? `–${item.end_time}` : ""}` : "Unavailable"}</strong><span>{item.reason || "No note"}</span></div>)}</div> : null}
      <p className={error ? styles.errorText : styles.successText} role="status">{error || message}</p>
    </section>
  );
}
