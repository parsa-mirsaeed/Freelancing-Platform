import type { ContractStatus, MemberRole, MilestoneStatus } from "@/lib/api/contracts";
import { productJson } from "@/lib/api/product-client";

export const CURRENT_PAYMENT_PROVIDER =
  process.env.NEXT_PUBLIC_PAYMENT_PROVIDER?.trim().toLowerCase() || "sandbox";

export interface MilestoneFinancialState {
  milestone_id: string;
  milestone_status: MilestoneStatus;
  contracted_amount_minor: number;
  currency: string;
  escrow_balance_minor: number;
  commission_bps: number | null;
}

export interface PaymentIntentResult {
  payment_intent_id: string;
  milestone_id: string;
  provider: string;
  provider_reference: string | null;
  amount_minor: number;
  currency: string;
  status: string;
}

export interface PaymentActionResult {
  payment_intent_id: string;
  provider: string;
  status: string;
  action: null | {
    kind: "stripe_payment_intent" | string;
    client_secret: string;
    publishable_key: string;
  };
}

export interface RefundResult {
  refund_id: string;
  milestone_id: string;
  provider: string;
  provider_reference: string | null;
  amount_minor: number;
  currency: string;
  status: string;
}

export interface WalletBalances {
  balances: Record<string, number>;
}

export interface PayoutResult {
  payout_id: string;
  provider: string;
  provider_reference: string | null;
  amount_minor: number;
  currency: string;
  status: string;
}

export type FinancialAction = "fund" | "release" | "refund";
export type FinancialMutationResult = MilestoneFinancialState | PaymentIntentResult | RefundResult;

export function canOfferFinancialAction({
  action,
  role,
  contractStatus,
  milestoneStatus,
  financial,
}: {
  action: FinancialAction;
  role: MemberRole;
  contractStatus: ContractStatus;
  milestoneStatus: MilestoneStatus;
  financial: MilestoneFinancialState;
}): boolean {
  if (role !== "employer" || contractStatus !== "ACTIVE") return false;
  if (financial.milestone_status !== milestoneStatus) return false;

  if (action === "fund") {
    return milestoneStatus === "CREATED" && financial.escrow_balance_minor === 0;
  }

  if (action === "refund") {
    return (
      milestoneStatus === "FUNDED" &&
      financial.escrow_balance_minor === financial.contracted_amount_minor
    );
  }

  return (
    milestoneStatus === "APPROVED" &&
    financial.escrow_balance_minor === financial.contracted_amount_minor
  );
}

export function financialActionAmount(
  action: FinancialAction,
  financial: MilestoneFinancialState,
): number {
  return action === "refund" ? financial.escrow_balance_minor : financial.contracted_amount_minor;
}

export function getMilestoneFinancials(
  milestoneId: string,
  signal?: AbortSignal,
): Promise<MilestoneFinancialState> {
  return productJson<MilestoneFinancialState>(`milestones/${milestoneId}/financials`, { signal });
}

export function mutateMilestoneFinancials(
  milestoneId: string,
  action: FinancialAction,
  idempotencyKey: string,
): Promise<FinancialMutationResult> {
  return productJson<FinancialMutationResult>(`milestones/${milestoneId}/${action}`, {
    method: "POST",
    headers: { "Idempotency-Key": idempotencyKey },
    body:
      action === "fund" || action === "refund"
        ? JSON.stringify({ provider: CURRENT_PAYMENT_PROVIDER })
        : undefined,
  });
}

export function getPaymentAction(paymentIntentId: string): Promise<PaymentActionResult> {
  return productJson<PaymentActionResult>(`payment-intents/${paymentIntentId}/action`);
}

export function getWallet(signal?: AbortSignal): Promise<WalletBalances> {
  return productJson<WalletBalances>("wallet", { signal });
}

export function requestPayout({
  amountMinor,
  currency,
  idempotencyKey,
}: {
  amountMinor: number;
  currency: string;
  idempotencyKey: string;
}): Promise<PayoutResult> {
  return productJson<PayoutResult>("payouts", {
    method: "POST",
    headers: { "Idempotency-Key": idempotencyKey },
    body: JSON.stringify({
      amount_minor: amountMinor,
      currency,
      provider: CURRENT_PAYMENT_PROVIDER,
    }),
  });
}
