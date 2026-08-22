import type { Metadata } from "next";

import { ProposalComposer } from "@/features/proposals/proposal-composer";

export const metadata: Metadata = {
  title: "Proposal draft",
  description: "Create a private versioned commercial proposal for an open project.",
};

type Params = Promise<{ projectId: string }>;

export default async function ProjectProposalPage({ params }: { params: Params }) {
  const { projectId } = await params;
  return <ProposalComposer projectId={projectId} />;
}
