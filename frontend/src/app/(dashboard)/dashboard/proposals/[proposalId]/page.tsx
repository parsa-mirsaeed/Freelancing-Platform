import type { Metadata } from "next";

import { ProposalDetail } from "@/features/proposals/proposal-detail";

export const metadata: Metadata = {
  title: "Proposal workspace",
  description: "Review immutable proposal versions and apply backend-governed transitions.",
};

type Params = Promise<{ proposalId: string }>;

export default async function ProposalWorkspacePage({ params }: { params: Params }) {
  const { proposalId } = await params;
  return <ProposalDetail proposalId={proposalId} />;
}
