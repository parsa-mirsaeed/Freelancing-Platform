import type { Metadata } from "next";

import { ContractWorkspace } from "@/features/contracts/contract-workspace";

export const metadata: Metadata = {
  title: "Project contract",
  description: "Open the immutable contract generated from the accepted project proposal.",
};

type Params = Promise<{ projectId: string }>;

export default async function ProjectContractPage({ params }: { params: Params }) {
  const { projectId } = await params;
  return <ContractWorkspace projectId={projectId} />;
}
