"use client";

import Link from "next/link";
import { useEffect, useState, type FormEvent } from "react";

import { useSession } from "@/components/providers/session-provider";
import { ProductApiError, productJson } from "@/lib/api/product-client";
import type { FreelancerProfile } from "@/lib/api/marketplace";
import type { Gig, GigTier } from "@/lib/api/work";
import { majorMoneyInputToMinor, minorMoneyInputValue } from "@/lib/intl";

import styles from "./workspace.module.css";

type PackageDraft = {
  tier: GigTier;
  enabled: boolean;
  price: string;
  deliveryDays: string;
  revisions: string;
  description: string;
};

type RequirementDraft = { prompt: string; required: boolean };

const DEFAULT_PACKAGES: PackageDraft[] = [
  { tier: "BASIC", enabled: true, price: "", deliveryDays: "7", revisions: "1", description: "" },
  { tier: "STANDARD", enabled: false, price: "", deliveryDays: "10", revisions: "2", description: "" },
  { tier: "PREMIUM", enabled: false, price: "", deliveryDays: "14", revisions: "3", description: "" },
];

function freshPackages(): PackageDraft[] {
  return DEFAULT_PACKAGES.map((item) => ({ ...item }));
}

export function GigWorkspace() {
  const { user, status } = useSession();
  const [items, setItems] = useState<Gig[]>([]);
  const [profileMissing, setProfileMissing] = useState(false);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");
  const [editingId, setEditingId] = useState<string | null>(null);
  const [title, setTitle] = useState("");
  const [description, setDescription] = useState("");
  const [currency, setCurrency] = useState("USD");
  const [active, setActive] = useState(true);
  const [packages, setPackages] = useState<PackageDraft[]>(freshPackages);
  const [requirements, setRequirements] = useState<RequirementDraft[]>([
    { prompt: "", required: true },
  ]);

  useEffect(() => {
    if (status !== "authenticated" || !user?.roles.includes("freelancer")) return;
    const controller = new AbortController();
    void Promise.all([
      productJson<{ items: Gig[] }>("gigs", { signal: controller.signal }),
      productJson<FreelancerProfile>("freelancers/me/profile", { signal: controller.signal }),
    ])
      .then(([gigs, profile]) => {
        setItems(gigs.items.filter((gig) => gig.freelancer_profile_id === profile.id));
        setProfileMissing(false);
        setLoading(false);
      })
      .catch((reason: unknown) => {
        if (controller.signal.aborted) return;
        if (reason instanceof ProductApiError && reason.status === 404) setProfileMissing(true);
        else setError(reason instanceof Error ? reason.message : "Unable to load services.");
        setLoading(false);
      });
    return () => controller.abort();
  }, [status, user]);

  function resetEditor() {
    setEditingId(null);
    setTitle("");
    setDescription("");
    setCurrency("USD");
    setActive(true);
    setPackages(freshPackages());
    setRequirements([{ prompt: "", required: true }]);
    setError("");
  }

  function editGig(gig: Gig) {
    const first = gig.packages[0];
    const normalizedCurrency = first?.currency ?? "USD";
    setEditingId(gig.id);
    setTitle(gig.title);
    setDescription(gig.description);
    setCurrency(normalizedCurrency);
    setActive(gig.is_active);
    setPackages(
      DEFAULT_PACKAGES.map((template) => {
        const existing = gig.packages.find((item) => item.tier === template.tier);
        if (!existing) return { ...template };
        return {
          tier: template.tier,
          enabled: true,
          price: minorMoneyInputValue(existing.amount_minor, existing.currency),
          deliveryDays: String(existing.delivery_days),
          revisions: String(existing.revisions),
          description: existing.description,
        };
      }),
    );
    setRequirements(
      gig.requirements.length
        ? gig.requirements.map((item) => ({ prompt: item.prompt, required: item.required }))
        : [{ prompt: "", required: true }],
    );
    setMessage("");
    setError("");
  }

  function updatePackage(tier: GigTier, patch: Partial<PackageDraft>) {
    setPackages((current) =>
      current.map((item) => (item.tier === tier ? { ...item, ...patch } : item)),
    );
  }

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setSaving(true);
    setError("");
    setMessage("");
    try {
      const normalizedCurrency = currency.trim().toUpperCase();
      if (normalizedCurrency.length !== 3) throw new RangeError("Currency must be a 3-letter code.");
      const selected = packages.filter((item) => item.enabled);
      if (!selected.some((item) => item.tier === "BASIC")) throw new RangeError("A Basic package is required.");
      const packagePayload = selected.map((item) => ({
        tier: item.tier,
        amount_minor: majorMoneyInputToMinor(item.price, normalizedCurrency),
        currency: normalizedCurrency,
        delivery_days: Number.parseInt(item.deliveryDays, 10),
        revisions: Number.parseInt(item.revisions, 10),
        description: item.description.trim(),
      }));
      if (packagePayload.some((item) => !Number.isInteger(item.delivery_days) || item.delivery_days < 1)) {
        throw new RangeError("Delivery days must be positive whole numbers.");
      }
      if (packagePayload.some((item) => !Number.isInteger(item.revisions) || item.revisions < 0)) {
        throw new RangeError("Revisions must be non-negative whole numbers.");
      }
      const requirementPayload = requirements
        .map((item) => ({ prompt: item.prompt.trim(), required: item.required }))
        .filter((item) => item.prompt.length > 0);
      const payload = {
        title: title.trim(),
        description: description.trim(),
        packages: packagePayload,
        requirements: requirementPayload,
        ...(editingId ? { is_active: active } : {}),
      };
      if (!payload.title || !payload.description) throw new RangeError("Title and description are required.");
      const saved = await productJson<Gig>(editingId ? `gigs/${editingId}` : "gigs", {
        method: editingId ? "PUT" : "POST",
        body: JSON.stringify(payload),
      });
      setItems((current) => {
        const found = current.some((item) => item.id === saved.id);
        return found ? current.map((item) => (item.id === saved.id ? saved : item)) : [saved, ...current];
      });
      setMessage(editingId ? "Service updated from authoritative backend state." : "Service published.");
      if (!editingId) resetEditor();
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Unable to save service.");
    } finally {
      setSaving(false);
    }
  }

  if (status === "loading") {
    return <section className={styles.loading} role="status">Opening your freelancer workspace…</section>;
  }
  if (status !== "authenticated" || !user) {
    return <section className={styles.loading}>Sign in with a freelancer account to manage services.</section>;
  }
  if (!user.roles.includes("freelancer")) {
    return <section className={styles.loading}>Service publishing is available to freelancer accounts.</section>;
  }
  if (loading) return <section className={styles.loading} role="status">Loading your active services…</section>;
  if (profileMissing) {
    return <section className={styles.loading}><h1>Create your professional profile first.</h1><p>A gig must belong to an existing freelancer profile.</p><Link href="/dashboard/profile">Open profile setup</Link></section>;
  }

  return (
    <div className={styles.workspace}>
      <section className={styles.workspaceIntro}>
        <div><p>Freelancer services</p><h1>Package expertise without hiding the commercial terms.</h1><span>Active services are publicly discoverable. Basic is required; Standard and Premium are optional. All package values are sent to Flask as integer minor units.</span></div>
        <Link href="/services">View public services ↗</Link>
      </section>

      <section className={styles.twoColumn}>
        <div className={styles.inventory}>
          <div className={styles.sectionTitle}><div><span>Active inventory</span><h2>Your published services</h2></div><button type="button" onClick={resetEditor}>New service</button></div>
          {items.length ? items.map((gig) => (
            <article className={styles.inventoryCard} key={gig.id}>
              <div><span>{gig.is_active ? "Active" : "Inactive until refresh"}</span><h3>{gig.title}</h3><p>{gig.description}</p></div>
              <div className={styles.inventoryActions}><Link href={`/services/${gig.id}`}>Public view</Link><button type="button" onClick={() => editGig(gig)}>Edit</button></div>
            </article>
          )) : <p className={styles.empty}>No active services yet. Publish the first one from the editor.</p>}
          <p className={styles.constraintNote}>The current backend list endpoint returns active gigs only. An inactive gig can be updated from its known direct URL, but it cannot be rediscovered from the list after refresh until a dedicated owner-history API exists.</p>
        </div>

        <form className={styles.editor} onSubmit={submit}>
          <div className={styles.sectionTitle}><div><span>{editingId ? "Edit service" : "New service"}</span><h2>{editingId ? "Update published terms" : "Build service packages"}</h2></div></div>
          {error ? <p className={styles.error} role="alert">{error}</p> : null}
          {message ? <p className={styles.success} role="status">{message}</p> : null}
          <label>Service title<input value={title} maxLength={160} onChange={(event) => setTitle(event.target.value)} required /></label>
          <label>Description<textarea value={description} rows={5} onChange={(event) => setDescription(event.target.value)} required /></label>
          <label className={styles.shortField}>Currency<input value={currency} maxLength={3} onChange={(event) => setCurrency(event.target.value.toUpperCase())} required /></label>
          {editingId ? <label className={styles.check}><input type="checkbox" checked={active} onChange={(event) => setActive(event.target.checked)} /> Keep service active</label> : null}

          <fieldset className={styles.packageEditor}><legend>Packages</legend>
            {packages.map((item) => (
              <div className={styles.packageRow} key={item.tier}>
                <div className={styles.packageHeading}><strong>{item.tier}</strong>{item.tier !== "BASIC" ? <label className={styles.check}><input type="checkbox" checked={item.enabled} onChange={(event) => updatePackage(item.tier, { enabled: event.target.checked })} /> Include</label> : <span>Required</span>}</div>
                {item.enabled ? <div className={styles.packageFields}>
                  <label>Price<input inputMode="decimal" value={item.price} onChange={(event) => updatePackage(item.tier, { price: event.target.value })} required /></label>
                  <label>Delivery days<input type="number" min="1" max="3650" value={item.deliveryDays} onChange={(event) => updatePackage(item.tier, { deliveryDays: event.target.value })} required /></label>
                  <label>Revisions<input type="number" min="0" max="1000" value={item.revisions} onChange={(event) => updatePackage(item.tier, { revisions: event.target.value })} required /></label>
                  <label className={styles.full}>Package description<textarea rows={2} value={item.description} onChange={(event) => updatePackage(item.tier, { description: event.target.value })} /></label>
                </div> : null}
              </div>
            ))}
          </fieldset>

          <fieldset className={styles.requirementEditor}><legend>Client requirements</legend>
            {requirements.map((item, index) => (
              <div className={styles.requirementRow} key={`requirement-${index}`}>
                <label>Prompt<input value={item.prompt} maxLength={500} onChange={(event) => setRequirements((current) => current.map((entry, entryIndex) => entryIndex === index ? { ...entry, prompt: event.target.value } : entry))} /></label>
                <label className={styles.check}><input type="checkbox" checked={item.required} onChange={(event) => setRequirements((current) => current.map((entry, entryIndex) => entryIndex === index ? { ...entry, required: event.target.checked } : entry))} /> Required</label>
                {requirements.length > 1 ? <button type="button" onClick={() => setRequirements((current) => current.filter((_, entryIndex) => entryIndex !== index))}>Remove</button> : null}
              </div>
            ))}
            <button className={styles.addRow} type="button" onClick={() => setRequirements((current) => [...current, { prompt: "", required: true }])} disabled={requirements.length >= 50}>Add requirement</button>
          </fieldset>
          <div className={styles.editorActions}><button type="submit" disabled={saving}>{saving ? "Saving…" : editingId ? "Save service" : "Publish service"}</button>{editingId ? <button type="button" onClick={resetEditor}>Cancel edit</button> : null}</div>
        </form>
      </section>
    </div>
  );
}
