import type { Metadata } from "next";

import { ContractWorkspace } from "@/features/contracts/contract-workspace";
import { ContractMoneyWorkspace } from "@/features/money/contract-money-workspace";

export const metadata: Metadata = {
  title: "Contract workspace",
  description: "Review immutable contract execution and backend-authoritative milestone finances.",
};

type Params = Promise<{ contractId: string }>;

export default async function ContractPage({ params }: { params: Params }) {
  const { contractId } = await params;
  return (
    <>
      <ContractWorkspace contractId={contractId} />
      <ContractMoneyWorkspace contractId={contractId} />
    </>
  );
}
