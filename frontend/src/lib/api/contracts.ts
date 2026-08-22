import { productJson } from "@/lib/api/product-client";

export type ContractStatus = "PENDING_SIGNATURES" | "ACTIVE" | "CANCELLED";
export type ContractRole = "EMPLOYER" | "FREELANCER";
export type MemberRole = "employer" | "freelancer";
export type MilestoneStatus =
  | "CREATED"
  | "FUNDED"
  | "IN_PROGRESS"
  | "SUBMITTED"
  | "CHANGES_REQUESTED"
  | "DISPUTED"
  | "APPROVED"
  | "RELEASE_PENDING"
  | "RELEASED";
export type MilestoneAction = "start" | "submit" | "request-changes" | "approve";

export interface ContractParty {
  user_id: string;
  role: ContractRole;
  required_signature: boolean;
}

export interface ContractSignature {
  id: string;
  user_id: string;
  signed_at: string;
  document_hash: string;
  signature_provider_reference: string | null;
}

export interface MilestoneEvent {
  id: string;
  actor_user_id: string | null;
  from_status: string | null;
  to_status: MilestoneStatus;
  note: string | null;
  created_at: string;
}

export interface Milestone {
  id: string;
  contract_version_id?: string;
  sequence: number;
  title: string;
  amount_minor: number;
  currency: string;
  delivery_days: number;
  status: MilestoneStatus;
  events: MilestoneEvent[];
}

export interface ContractSnapshot {
  schema_version?: number;
  source?: {
    project_id?: string;
    proposal_id?: string;
    proposal_version_id?: string;
    proposal_version?: number;
  };
  scope?: {
    project_title?: string;
    project_description?: string;
    proposal_cover_letter?: string;
  };
  price?: { amount_minor?: number };
  currency?: string;
  delivery_days?: number;
  milestones?: Array<{
    sequence?: number;
    title?: string;
    amount_minor?: number;
    currency?: string;
    delivery_days?: number;
  }>;
  commission?: { platform_bps?: number };
  refund_terms?: unknown;
  dispute_terms?: unknown;
  attachments?: Array<{
    id?: string;
    object_key?: string;
    mime_type?: string;
    file_size_bytes?: number;
    scan_status?: string;
  }>;
}

export interface Contract {
  id: string;
  project_id: string;
  accepted_proposal_id: string;
  employer_user_id: string;
  freelancer_user_id: string;
  status: ContractStatus;
  current_version: number;
  created_at: string;
  activated_at: string | null;
  cancelled_at: string | null;
  parties: ContractParty[];
  version: {
    id: string;
    version_number: number;
    document_hash: string;
    snapshot: ContractSnapshot;
    created_at: string;
    signatures: ContractSignature[];
    milestones: Milestone[];
  };
}

export function memberRoleForContract(contract: Contract, userId: string): MemberRole | null {
  if (contract.freelancer_user_id === userId) return "freelancer";
  if (contract.employer_user_id === userId) return "employer";
  return null;
}

export function hasSignedCurrentVersion(contract: Contract, userId: string): boolean {
  return contract.version.signatures.some(
    (signature) =>
      signature.user_id === userId && signature.document_hash === contract.version.document_hash,
  );
}

export function canSignCurrentVersion(contract: Contract, userId: string): boolean {
  if (contract.status === "CANCELLED" || hasSignedCurrentVersion(contract, userId)) return false;
  return contract.parties.some(
    (party) => party.user_id === userId && party.required_signature,
  );
}

export function canOfferContractCancellation(contract: Contract, role: MemberRole): boolean {
  if (role !== "employer" || contract.status === "CANCELLED") return false;
  return contract.version.milestones.every((milestone) => milestone.status === "CREATED");
}

export function milestoneActions(
  milestone: Milestone,
  role: MemberRole,
  contractStatus: ContractStatus,
): MilestoneAction[] {
  if (contractStatus !== "ACTIVE") return [];
  if (role === "freelancer") {
    if (milestone.status === "FUNDED") return ["start"];
    if (milestone.status === "IN_PROGRESS" || milestone.status === "CHANGES_REQUESTED") {
      return ["submit"];
    }
    return [];
  }
  if (milestone.status === "SUBMITTED") return ["request-changes", "approve"];
  return [];
}

export async function signContract(
  contract: Contract,
  idempotencyKey: string,
): Promise<Contract> {
  return productJson<Contract>(`contracts/${contract.id}/sign`, {
    method: "POST",
    headers: { "Idempotency-Key": idempotencyKey },
    body: JSON.stringify({ document_hash: contract.version.document_hash }),
  });
}

export async function cancelContract(contractId: string): Promise<Contract> {
  return productJson<Contract>(`contracts/${contractId}/cancel`, { method: "POST" });
}

export async function transitionMilestone(
  milestoneId: string,
  action: MilestoneAction,
  note?: string,
): Promise<Milestone> {
  const body =
    action === "submit" || action === "request-changes"
      ? JSON.stringify({ note: note ?? "" })
      : undefined;
  return productJson<Milestone>(`milestones/${milestoneId}/${action}`, {
    method: "POST",
    body,
  });
}
