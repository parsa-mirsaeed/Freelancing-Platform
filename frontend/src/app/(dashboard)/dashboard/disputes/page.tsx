import type { Metadata } from "next";

import { DisputesWorkspace } from "@/features/disputes/disputes-workspace";

export const metadata: Metadata = {
  title: "Disputes",
  description: "Evidence collection, frozen milestone review, and audited dispute arbitration.",
};

type SearchParams = Promise<{ contract?: string; dispute?: string; project?: string }>;

export default async function DisputesPage({ searchParams }: { searchParams: SearchParams }) {
  const params = await searchParams;
  return (
    <DisputesWorkspace
      contractId={params.contract?.trim() || undefined}
      disputeId={params.dispute?.trim() || undefined}
      projectId={params.project?.trim() || undefined}
    />
  );
}
