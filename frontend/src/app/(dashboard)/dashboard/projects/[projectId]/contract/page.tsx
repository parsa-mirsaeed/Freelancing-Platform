import type { Metadata } from "next";

import { ContractWorkspace } from "@/features/contracts/contract-workspace";
import { ContractMoneyWorkspace } from "@/features/money/contract-money-workspace";

export const metadata: Metadata = {
  title: "Project contract",
  description: "Open immutable contract execution and backend-authoritative milestone finances.",
};

type Params = Promise<{ projectId: string }>;

export default async function ProjectContractPage({ params }: { params: Params }) {
  const { projectId } = await params;
  return (
    <>
      <ContractWorkspace projectId={projectId} />
      <ContractMoneyWorkspace projectId={projectId} />
    </>
  );
}
