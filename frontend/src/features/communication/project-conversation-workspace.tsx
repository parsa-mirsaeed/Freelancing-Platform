"use client";

import { useEffect, useState } from "react";

import { openProjectConversation } from "@/lib/api/communication";

import { CommunicationWorkspace } from "./communication-workspace";
import styles from "./communication.module.css";

export function ProjectConversationWorkspace({ projectId }: { projectId: string }) {
  const [conversationId, setConversationId] = useState("");
  const [error, setError] = useState("");

  useEffect(() => {
    let cancelled = false;
    void openProjectConversation(projectId)
      .then((conversation) => {
        if (cancelled) return;
        setConversationId(conversation.id);
        setError("");
      })
      .catch((reason: unknown) => {
        if (cancelled) return;
        setError(reason instanceof Error ? reason.message : "Unable to open project conversation.");
      });
    return () => {
      cancelled = true;
    };
  }, [projectId]);

  if (error) {
    return <main className={styles.page}><p className={styles.errorBanner} role="alert">{error}</p></main>;
  }
  if (!conversationId) {
    return <main className={styles.page}><p className={styles.empty} role="status">Opening project conversation…</p></main>;
  }
  return <CommunicationWorkspace conversationId={conversationId} />;
}
