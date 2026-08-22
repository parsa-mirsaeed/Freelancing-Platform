"use client";

import { useState, type FormEvent } from "react";

import {
  buildProposalPayload,
  type MilestoneDraft,
  type ProposalDraft,
  type ProposalWritePayload,
} from "@/lib/api/proposals";

import styles from "./proposals.module.css";

function blankMilestone(): MilestoneDraft {
  return { title: "", amount: "", deliveryDays: "7" };
}

export interface ProposalEditorInitial {
  amount?: string;
  currency?: string;
  deliveryDays?: string;
  coverLetter?: string;
  milestones?: MilestoneDraft[];
}

export function ProposalEditor({
  projectCurrency,
  initial,
  submitLabel,
  busy,
  onSubmit,
}: {
  projectCurrency: string | null;
  initial?: ProposalEditorInitial;
  submitLabel: string;
  busy: boolean;
  onSubmit: (payload: ProposalWritePayload) => Promise<void>;
}) {
  const [amount, setAmount] = useState(initial?.amount ?? "");
  const [currency, setCurrency] = useState(initial?.currency ?? projectCurrency ?? "USD");
  const [deliveryDays, setDeliveryDays] = useState(initial?.deliveryDays ?? "14");
  const [coverLetter, setCoverLetter] = useState(initial?.coverLetter ?? "");
  const [milestones, setMilestones] = useState<MilestoneDraft[]>(initial?.milestones ?? []);
  const [error, setError] = useState("");

  function updateMilestone(index: number, patch: Partial<MilestoneDraft>) {
    setMilestones((current) =>
      current.map((item, itemIndex) => (itemIndex === index ? { ...item, ...patch } : item)),
    );
  }

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError("");
    try {
      const draft: ProposalDraft = {
        amount,
        currency,
        deliveryDays,
        coverLetter,
        milestones,
      };
      await onSubmit(buildProposalPayload(draft, projectCurrency));
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Proposal terms are invalid.");
    }
  }

  return (
    <form className={styles.editor} onSubmit={submit}>
      {error ? <p className={styles.error} role="alert">{error}</p> : null}
      <div className={styles.commercialGrid}>
        <label>
          Proposal amount
          <input
            value={amount}
            onChange={(event) => setAmount(event.target.value)}
            inputMode="decimal"
            placeholder="12000"
            required
          />
        </label>
        <label>
          Currency
          <input
            value={projectCurrency ?? currency}
            onChange={(event) => setCurrency(event.target.value.toUpperCase())}
            maxLength={3}
            readOnly={Boolean(projectCurrency)}
            required
          />
        </label>
        <label>
          Delivery days
          <input
            value={deliveryDays}
            onChange={(event) => setDeliveryDays(event.target.value)}
            inputMode="numeric"
            required
          />
        </label>
      </div>

      <label className={styles.coverLetter}>
        Cover letter
        <textarea
          value={coverLetter}
          onChange={(event) => setCoverLetter(event.target.value)}
          rows={7}
          placeholder="Explain your approach, relevant experience, and how you would de-risk delivery."
        />
      </label>

      <fieldset className={styles.milestones}>
        <div className={styles.fieldsetHeading}>
          <div>
            <legend>Milestone plan</legend>
            <p>Optional. If used, milestone amounts must equal the proposal total exactly.</p>
          </div>
          <button
            type="button"
            onClick={() => setMilestones((current) => [...current, blankMilestone()])}
          >
            + Add milestone
          </button>
        </div>
        {milestones.length ? (
          <div className={styles.milestoneList}>
            {milestones.map((milestone, index) => (
              <div className={styles.milestoneRow} key={`milestone-${index + 1}`}>
                <span>{String(index + 1).padStart(2, "0")}</span>
                <label>
                  Title
                  <input
                    value={milestone.title}
                    maxLength={180}
                    onChange={(event) => updateMilestone(index, { title: event.target.value })}
                    required
                  />
                </label>
                <label>
                  Amount
                  <input
                    value={milestone.amount}
                    inputMode="decimal"
                    onChange={(event) => updateMilestone(index, { amount: event.target.value })}
                    required
                  />
                </label>
                <label>
                  Days
                  <input
                    value={milestone.deliveryDays}
                    inputMode="numeric"
                    onChange={(event) => updateMilestone(index, { deliveryDays: event.target.value })}
                    required
                  />
                </label>
                <button
                  className={styles.removeButton}
                  type="button"
                  onClick={() =>
                    setMilestones((current) => current.filter((_, itemIndex) => itemIndex !== index))
                  }
                >
                  Remove
                </button>
              </div>
            ))}
          </div>
        ) : (
          <p className={styles.emptyMilestones}>No milestone split. The proposal can still be submitted as one commercial amount.</p>
        )}
      </fieldset>

      <div className={styles.editorFooter}>
        <p>
          Saving here writes commercial terms to the backend. Historical proposal versions are never
          overwritten.
        </p>
        <button type="submit" disabled={busy}>{busy ? "Saving…" : submitLabel}</button>
      </div>
    </form>
  );
}
