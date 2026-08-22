import type { Metadata } from "next";

import { ContractWorkspace } from "@/features/contracts/contract-workspace";

export const metadata: Metadata = {
  title: "Contract workspace",
  description: "Review the immutable contract, signatures, and backend-governed milestone execution.",
};

type Params = Promise<{ contractId: string }>;

export default async function ContractPage({ params }: { params: Params }) {
  const { contractId } = await params;
  return <ContractWorkspace contractId={contractId} />;
}
