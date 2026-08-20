"use client";

import { useState, type FormEvent } from "react";

import type { PortfolioItem } from "@/lib/api/marketplace";
import { ProductApiError, productJson } from "@/features/profile/profile-api";

import styles from "./profile-workspace.module.css";

export function PortfolioEditor({ initialItems }: { initialItems: PortfolioItem[] }) {
  const [items, setItems] = useState(initialItems);
  const [title, setTitle] = useState("");
  const [description, setDescription] = useState("");
  const [externalUrl, setExternalUrl] = useState("");
  const [confirming, setConfirming] = useState<string | null>(null);
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");

  async function create(event: FormEvent<HTMLFormElement>) {
    event.preventDefault(); setMessage(""); setError("");
    try {
      const item = await productJson<PortfolioItem>("freelancers/me/portfolio", {
        method: "POST",
        body: JSON.stringify({ title: title.trim(), description: description.trim(), external_url: externalUrl.trim() || null }),
      });
      setItems((current) => [item, ...current]);
      setTitle(""); setDescription(""); setExternalUrl(""); setMessage("Portfolio item published.");
    } catch (caught) { setError(caught instanceof ProductApiError ? caught.message : "Portfolio item could not be created."); }
  }

  async function remove(itemId: string) {
    setMessage(""); setError("");
    try {
      await productJson<void>(`portfolio/${itemId}`, { method: "DELETE" });
      setItems((current) => current.filter((item) => item.id !== itemId));
      setConfirming(null); setMessage("Portfolio item removed.");
    } catch (caught) { setError(caught instanceof ProductApiError ? caught.message : "Portfolio item could not be removed."); }
  }

  return (
    <section className={styles.formSection}>
      <div className={styles.sectionTitle}><div><span>Proof of work</span><h2>Portfolio</h2></div><p>Publish project context and external work now. SAFE file attachment/download is added with the communication/files slice.</p></div>
      <form className={styles.portfolioForm} onSubmit={create}>
        <label><span>Title</span><input required maxLength={160} value={title} onChange={(event) => setTitle(event.target.value)} placeholder="Mobile banking design system" /></label>
        <label><span>External URL</span><input type="url" maxLength={2048} value={externalUrl} onChange={(event) => setExternalUrl(event.target.value)} placeholder="https://…" /></label>
        <label className={styles.fullField}><span>Description</span><textarea rows={4} value={description} onChange={(event) => setDescription(event.target.value)} /></label>
        <button type="submit">Add portfolio item</button>
      </form>
      <div className={styles.portfolioList}>
        {items.map((item) => <article key={item.id}><div><h3>{item.title}</h3><p>{item.description || "No description."}</p>{item.external_url ? <a href={item.external_url} target="_blank" rel="noreferrer">Open link ↗</a> : null}</div><div className={styles.removeArea}>{confirming === item.id ? <><span>Remove permanently?</span><button className={styles.dangerButton} type="button" onClick={() => void remove(item.id)}>Confirm remove</button><button className={styles.quietButton} type="button" onClick={() => setConfirming(null)}>Cancel</button></> : <button className={styles.quietButton} type="button" onClick={() => setConfirming(item.id)}>Remove</button>}</div></article>)}
        {items.length === 0 ? <p className={styles.emptyText}>No portfolio items yet.</p> : null}
      </div>
      <p className={error ? styles.errorText : styles.successText} role="status">{error || message}</p>
    </section>
  );
}
