import type { Metadata } from "next";

import { ProposalCompare } from "@/features/proposals/proposal-compare";

export const metadata: Metadata = {
  title: "Proposal comparison",
  description: "Compare private versioned proposals for an owned project.",
};

type Params = Promise<{ projectId: string }>;

export default async function ProjectProposalsPage({ params }: { params: Params }) {
  const { projectId } = await params;
  return <ProposalCompare projectId={projectId} />;
}
