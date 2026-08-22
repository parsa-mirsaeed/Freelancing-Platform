"use client";

import { useEffect, useRef, useState } from "react";

import type { Message, NotificationItem } from "@/lib/api/communication";
import {
  configuredRealtimeUrl,
  RealtimeSocketClient,
  type RealtimeState,
} from "@/lib/realtime/socket-client";

type ReceiptEvent = {
  conversation_id: string;
  user_id: string;
  through_sequence: number;
};

type PresenceResult = {
  ok: boolean;
  members?: Array<{ user_id: string; online: boolean }>;
  error?: { detail?: string };
};

type MessageAck = {
  ok: boolean;
  message?: Message;
  error?: { detail?: string };
};

export function useRealtimeConversation({
  conversationId,
  userId,
  onMessage,
  onReceipt,
  onNotification,
}: {
  conversationId: string;
  userId: string;
  onMessage: (message: Message) => void;
  onReceipt: (event: ReceiptEvent, type: "DELIVERED" | "READ") => void;
  onNotification: (notification: NotificationItem) => void;
}) {
  const [state, setState] = useState<RealtimeState>(configuredRealtimeUrl() ? "connecting" : "fallback");
  const [peerOnline, setPeerOnline] = useState<boolean | null>(null);
  const clientRef = useRef<RealtimeSocketClient | null>(null);
  const callbacks = useRef({ onMessage, onReceipt, onNotification });

  useEffect(() => {
    callbacks.current = { onMessage, onReceipt, onNotification };
  }, [onMessage, onNotification, onReceipt]);

  useEffect(() => {
    const baseUrl = configuredRealtimeUrl();
    if (!baseUrl || !conversationId || !userId) return;
    const client = new RealtimeSocketClient(baseUrl, conversationId, {
      onState: (next) => {
        setState(next);
        if (next !== "live") return;
        void client
          .emit<PresenceResult>("presence.query", { conversation_id: conversationId })
          .then((result) => {
            if (!result.ok || !result.members) return;
            const peer = result.members.find((member) => member.user_id !== userId);
            setPeerOnline(peer?.online ?? null);
          })
          .catch(() => undefined);
      },
      onEvent: (event, payload) => {
        if (event === "message.created") {
          const created = payload as Message;
          callbacks.current.onMessage(created);
          if (created.sender_user_id !== userId) {
            void client
              .emit("message.read", {
                conversation_id: conversationId,
                through_sequence: created.sequence,
              })
              .catch(() => undefined);
          }
          return;
        }
        if (event === "message.delivered") {
          callbacks.current.onReceipt(payload as ReceiptEvent, "DELIVERED");
          return;
        }
        if (event === "message.read") {
          callbacks.current.onReceipt(payload as ReceiptEvent, "READ");
          return;
        }
        if (event === "notification.created") {
          callbacks.current.onNotification(payload as NotificationItem);
        }
      },
    });
    clientRef.current = client;
    client.start();
    return () => {
      client.stop();
      if (clientRef.current === client) clientRef.current = null;
    };
  }, [conversationId, userId]);

  async function sendLive({
    clientMessageId,
    body,
    attachmentIds,
  }: {
    clientMessageId: string;
    body: string;
    attachmentIds: string[];
  }): Promise<Message | null> {
    const client = clientRef.current;
    if (!client?.isLive()) return null;
    const ack = await client.emit<MessageAck>("message.send", {
      conversation_id: conversationId,
      client_message_id: clientMessageId,
      body,
      attachment_ids: attachmentIds,
    });
    if (!ack.ok || !ack.message) throw new Error(ack.error?.detail || "Realtime message was rejected.");
    return ack.message;
  }

  return { state, peerOnline, sendLive };
}
