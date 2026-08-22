import { majorMoneyInputToMinor } from "@/lib/intl";

export type ProposalStatus =
  | "DRAFT"
  | "SUBMITTED"
  | "UNDER_NEGOTIATION"
  | "WITHDRAWN"
  | "REJECTED"
  | "ACCEPTED";

export type ProposalAction = "submit" | "negotiate" | "withdraw" | "reject" | "accept";
export type ProposalActor = "freelancer" | "employer";

export interface ProposalMilestone {
  id: string;
  sequence: number;
  title: string;
  amount_minor: number;
  delivery_days: number;
}

export interface ProposalVersion {
  id: string;
  version_number: number;
  amount_minor: number;
  currency: string;
  delivery_days: number;
  cover_letter: string;
  milestones: ProposalMilestone[];
}

export interface Proposal {
  id: string;
  project_id: string;
  freelancer_user_id: string;
  status: ProposalStatus;
  current_version: number;
  versions: ProposalVersion[];
}

export interface MilestoneDraft {
  title: string;
  amount: string;
  deliveryDays: string;
}

export interface ProposalDraft {
  amount: string;
  currency: string;
  deliveryDays: string;
  coverLetter: string;
  milestones: MilestoneDraft[];
}

export interface ProposalWritePayload {
  amount_minor: number;
  currency: string;
  delivery_days: number;
  cover_letter: string;
  milestones: Array<{
    title: string;
    amount_minor: number;
    delivery_days: number;
  }>;
}

const ACTIONS: Record<ProposalActor, Partial<Record<ProposalStatus, ProposalAction[]>>> = {
  freelancer: {
    DRAFT: ["submit"],
    SUBMITTED: ["withdraw"],
    UNDER_NEGOTIATION: ["withdraw"],
  },
  employer: {
    SUBMITTED: ["negotiate", "reject", "accept"],
    UNDER_NEGOTIATION: ["reject", "accept"],
  },
};

export function proposalActions(status: ProposalStatus, actor: ProposalActor): ProposalAction[] {
  return ACTIONS[actor][status] ?? [];
}

export function canAppendProposalVersion(status: ProposalStatus, actor: ProposalActor): boolean {
  return actor === "freelancer" && (status === "DRAFT" || status === "UNDER_NEGOTIATION");
}

export function currentProposalVersion(proposal: Proposal): ProposalVersion {
  const version = proposal.versions.find((item) => item.version_number === proposal.current_version);
  if (!version) throw new RangeError("Current proposal version is missing from the response.");
  return version;
}

function positiveWholeNumber(value: string, label: string): number {
  if (!/^\d+$/.test(value.trim())) throw new RangeError(`${label} must be a whole number.`);
  const parsed = Number.parseInt(value, 10);
  if (!Number.isSafeInteger(parsed) || parsed < 1 || parsed > 3650) {
    throw new RangeError(`${label} must be between 1 and 3650 days.`);
  }
  return parsed;
}

export function buildProposalPayload(
  draft: ProposalDraft,
  projectCurrency: string | null,
): ProposalWritePayload {
  const currency = (projectCurrency ?? draft.currency).trim().toUpperCase();
  if (currency.length !== 3) throw new RangeError("Proposal currency must be a 3-letter code.");
  if (projectCurrency && currency !== projectCurrency.toUpperCase()) {
    throw new RangeError(`Proposal currency must match the project currency (${projectCurrency}).`);
  }

  const amountMinor = majorMoneyInputToMinor(draft.amount, currency);
  const deliveryDays = positiveWholeNumber(draft.deliveryDays, "Delivery time");
  const milestones = draft.milestones
    .filter((item) => item.title.trim() || item.amount.trim() || item.deliveryDays.trim())
    .map((item, index) => {
      const title = item.title.trim();
      if (!title) throw new RangeError(`Milestone ${index + 1} needs a title.`);
      return {
        title,
        amount_minor: majorMoneyInputToMinor(item.amount, currency),
        delivery_days: positiveWholeNumber(item.deliveryDays, `Milestone ${index + 1} delivery time`),
      };
    });

  if (milestones.length > 50) throw new RangeError("A proposal may contain at most 50 milestones.");
  if (milestones.length && milestones.reduce((sum, item) => sum + item.amount_minor, 0) !== amountMinor) {
    throw new RangeError("Milestone amounts must add up exactly to the proposal amount.");
  }

  return {
    amount_minor: amountMinor,
    currency,
    delivery_days: deliveryDays,
    cover_letter: draft.coverLetter.trim(),
    milestones,
  };
}
