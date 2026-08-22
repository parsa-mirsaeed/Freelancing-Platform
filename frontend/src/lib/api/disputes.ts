import { productJson } from "@/lib/api/product-client";

export type DisputeStatus =
  | "OPEN"
  | "EVIDENCE_COLLECTION"
  | "UNDER_REVIEW"
  | "NEED_MORE_INFO"
  | "RESOLVED";

export type DisputeOutcome = "RELEASE_TO_FREELANCER" | "REFUND_CLIENT" | "SPLIT";

export interface DisputeParty {
  user_id: string;
  role: "EMPLOYER" | "FREELANCER" | string;
}

export interface DisputeEvidence {
  id: string;
  file_id: string;
  submitted_by_user_id: string;
  note: string;
  created_at: string;
}

export interface DisputeEvent {
  event_type: string;
  from_status: string | null;
  to_status: string | null;
  reason: string;
  created_at: string;
}

export interface DisputeDecision {
  id: string;
  administrator_user_id: string;
  outcome: DisputeOutcome;
  freelancer_award_minor: number;
  freelancer_net_minor: number;
  client_refund_minor: number;
  commission_minor: number;
  currency: string;
  journal_transaction_id: string;
  refund_id: string | null;
  reason: string;
  created_at: string;
}

export interface DisputeMilestoneSummary {
  id: string;
  sequence: number;
  title: string;
  amount_minor: number;
  currency: string;
  status: string;
}

export interface DisputeCase {
  id: string;
  milestone_id: string;
  contract_id: string;
  opened_by_user_id: string;
  status: DisputeStatus;
  reason: string;
  created_at: string;
  resolved_at: string | null;
  parties: DisputeParty[];
  evidence: DisputeEvidence[];
  events: DisputeEvent[];
  decision: DisputeDecision | null;
  milestone?: DisputeMilestoneSummary;
}

export interface DisputePage {
  items: DisputeCase[];
  next_after: string | null;
}

export interface FileObject {
  id: string;
  original_name: string;
  mime_type: string;
  size_bytes: number;
  sha256: string | null;
  purpose: string;
  status: "QUARANTINED" | "SCANNING" | "SAFE" | "REJECTED" | string;
  rejection_reason: string | null;
  created_at: string;
}

export interface UploadReservation {
  file: FileObject;
  upload_url: string;
}

export interface DownloadReservation {
  file: FileObject;
  download_url: string;
}

export function listDisputes({
  after,
  limit = 50,
  status,
  signal,
}: {
  after?: string;
  limit?: number;
  status?: DisputeStatus;
  signal?: AbortSignal;
} = {}): Promise<DisputePage> {
  const query = new URLSearchParams({ limit: String(limit) });
  if (after) query.set("after", after);
  if (status) query.set("status", status);
  return productJson<DisputePage>(`disputes?${query}`, { signal });
}

export function getDispute(disputeId: string, signal?: AbortSignal): Promise<DisputeCase> {
  return productJson<DisputeCase>(`disputes/${disputeId}`, { signal });
}

export function openDispute(milestoneId: string, reason: string): Promise<DisputeCase> {
  return productJson<DisputeCase>(`milestones/${milestoneId}/disputes`, {
    method: "POST",
    body: JSON.stringify({ reason }),
  });
}

export function requestEvidenceUpload(file: File): Promise<UploadReservation> {
  return productJson<UploadReservation>("files/uploads", {
    method: "POST",
    body: JSON.stringify({
      original_name: file.name,
      mime_type: file.type,
      size_bytes: file.size,
      purpose: "DISPUTE_EVIDENCE",
    }),
  });
}

export async function uploadEvidenceObject(
  reservation: UploadReservation,
  file: File,
): Promise<FileObject> {
  const uploaded = await fetch(reservation.upload_url, {
    method: "PUT",
    headers: { "Content-Type": file.type },
    body: file,
  });
  if (!uploaded.ok) throw new Error(`Evidence upload failed with ${uploaded.status}.`);
  return productJson<FileObject>(`files/${reservation.file.id}/complete`, { method: "POST" });
}

export function getEvidenceDownload(fileId: string): Promise<DownloadReservation> {
  return productJson<DownloadReservation>(`files/${fileId}`);
}

export function attachEvidence(
  disputeId: string,
  fileId: string,
  note: string,
): Promise<DisputeEvidence> {
  return productJson<DisputeEvidence>(`disputes/${disputeId}/evidence`, {
    method: "POST",
    body: JSON.stringify({ file_id: fileId, note }),
  });
}

export function transitionDispute(
  disputeId: string,
  toStatus: DisputeStatus,
  reason: string,
): Promise<DisputeCase> {
  return productJson<DisputeCase>(`disputes/${disputeId}/transitions`, {
    method: "POST",
    body: JSON.stringify({ to_status: toStatus, reason }),
  });
}

export function resolveDispute({
  disputeId,
  outcome,
  reason,
  freelancerAwardMinor,
  clientRefundMinor,
  idempotencyKey,
}: {
  disputeId: string;
  outcome: DisputeOutcome;
  reason: string;
  freelancerAwardMinor?: number;
  clientRefundMinor?: number;
  idempotencyKey: string;
}): Promise<DisputeCase> {
  return productJson<DisputeCase>(`disputes/${disputeId}/resolve`, {
    method: "POST",
    headers: { "Idempotency-Key": idempotencyKey },
    body: JSON.stringify({
      outcome,
      reason,
      freelancer_award_minor: freelancerAwardMinor ?? null,
      client_refund_minor: clientRefundMinor ?? null,
    }),
  });
}
