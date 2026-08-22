import type { Metadata } from "next";

import { CommunicationWorkspace } from "@/features/communication/communication-workspace";
import { ProjectConversationWorkspace } from "@/features/communication/project-conversation-workspace";

export const metadata: Metadata = {
  title: "Messages & notifications",
  description: "Private contract conversations, SAFE attachments, receipts, and notification preferences.",
};

type SearchParams = Promise<{ contract?: string; conversation?: string; project?: string }>;

export default async function MessagesPage({ searchParams }: { searchParams: SearchParams }) {
  const params = await searchParams;
  const projectId = params.project?.trim();
  if (projectId) return <ProjectConversationWorkspace projectId={projectId} />;
  return (
    <CommunicationWorkspace
      contractId={params.contract?.trim() || undefined}
      conversationId={params.conversation?.trim() || undefined}
    />
  );
}
