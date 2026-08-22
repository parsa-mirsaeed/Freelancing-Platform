"use client";

import { useEffect, useMemo, useRef, useState } from "react";

import { useSession } from "@/components/providers/session-provider";
import {
  getAttachmentDownload,
  listConversations,
  listMessages,
  listNotificationPreferences,
  listNotifications,
  markConversationRead,
  markNotificationRead,
  openContractConversation,
  requestMessageUpload,
  sendMessage,
  setNotificationPreference,
  uploadReservedFile,
  type Conversation,
  type FileObject,
  type Message,
  type MessageReceipt,
  type NotificationItem,
  type NotificationPreference,
} from "@/lib/api/communication";
import { formatDateTime } from "@/lib/intl";

import styles from "./communication.module.css";
import { useRealtimeConversation } from "./use-realtime-conversation";

type StagedFile = Pick<FileObject, "id" | "original_name" | "status">;
type ReceiptEvent = { conversation_id: string; user_id: string; through_sequence: number };

const NOTIFICATION_CHANNELS = ["IN_APP", "EMAIL", "PUSH", "SMS"] as const;

function mergeMessages(current: Message[], incoming: Message[]): Message[] {
  const byId = new Map(current.map((item) => [item.id, item]));
  for (const item of incoming) byId.set(item.id, item);
  return [...byId.values()].sort((a, b) => a.sequence - b.sequence);
}

function mergeNotifications(current: NotificationItem[], incoming: NotificationItem[]): NotificationItem[] {
  const byId = new Map(current.map((item) => [item.id, item]));
  for (const item of incoming) byId.set(item.id, item);
  return [...byId.values()].sort((a, b) => a.created_at.localeCompare(b.created_at));
}

function conversationLabel(conversation: Conversation, userId: string): string {
  const other = conversation.members.find((member) => member.user_id !== userId);
  return other ? `Conversation with ${other.user_id.slice(0, 8)}…` : "Contract conversation";
}

function receiptLabel(message: Message, userId: string): string {
  if (message.sender_user_id !== userId) return `Sequence ${message.sequence}`;
  const peerReceipts = message.receipts.filter((receipt) => receipt.user_id !== userId);
  if (peerReceipts.some((receipt) => receipt.type === "READ")) return "Read";
  if (peerReceipts.some((receipt) => receipt.type === "DELIVERED")) return "Delivered";
  return "Persisted";
}

function applyReceipt(
  current: Message[],
  event: ReceiptEvent,
  type: "DELIVERED" | "READ",
): Message[] {
  const createdAt = new Date().toISOString();
  return current.map((message) => {
    if (message.conversation_id !== event.conversation_id || message.sequence > event.through_sequence) {
      return message;
    }
    const withoutOlder = message.receipts.filter(
      (receipt) =>
        !(
          receipt.user_id === event.user_id &&
          (receipt.type === type || (type === "READ" && receipt.type === "DELIVERED"))
        ),
    );
    const receipt: MessageReceipt = { user_id: event.user_id, type, created_at: createdAt };
    return { ...message, receipts: [...withoutOlder, receipt] };
  });
}

export function CommunicationWorkspace({
  contractId,
  conversationId,
}: {
  contractId?: string;
  conversationId?: string;
}) {
  const { user, status } = useSession();
  const [conversations, setConversations] = useState<Conversation[]>([]);
  const [selectedId, setSelectedId] = useState(conversationId ?? "");
  const [messages, setMessages] = useState<Message[]>([]);
  const [notifications, setNotifications] = useState<NotificationItem[]>([]);
  const [preferences, setPreferences] = useState<NotificationPreference[]>([]);
  const [body, setBody] = useState("");
  const [stagedFiles, setStagedFiles] = useState<StagedFile[]>([]);
  const [busy, setBusy] = useState("");
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");
  const pendingClientMessageId = useRef("");
  const latestSequence = useRef(0);

  const realtime = useRealtimeConversation({
    conversationId: selectedId,
    userId: user?.id ?? "",
    onMessage: (created) => {
      latestSequence.current = Math.max(latestSequence.current, created.sequence);
      setMessages((current) => mergeMessages(current, [created]));
    },
    onReceipt: (event, type) => {
      setMessages((current) => applyReceipt(current, event, type));
    },
    onNotification: (notification) => {
      setNotifications((current) => mergeNotifications(current, [notification]));
    },
  });

  useEffect(() => {
    if (status !== "authenticated" || !user) return;
    const controller = new AbortController();
    const conversationPromise = contractId
      ? openContractConversation(contractId).then(async (opened) => {
          const listed = await listConversations(controller.signal);
          return { listed, opened };
        })
      : listConversations(controller.signal).then((listed) => ({ listed, opened: null }));

    void Promise.all([
      conversationPromise,
      listNotifications(controller.signal),
      listNotificationPreferences(controller.signal),
    ])
      .then(([conversationResult, notificationResult, preferenceResult]) => {
        if (controller.signal.aborted) return;
        const nextConversations = [...conversationResult.listed];
        if (
          conversationResult.opened &&
          !nextConversations.some((item) => item.id === conversationResult.opened?.id)
        ) {
          nextConversations.unshift(conversationResult.opened);
        }
        setConversations(nextConversations);
        setNotifications(notificationResult);
        setPreferences(preferenceResult);
        setSelectedId((current) =>
          current || conversationResult.opened?.id || nextConversations[0]?.id || "",
        );
        setError("");
      })
      .catch((reason: unknown) => {
        if (controller.signal.aborted) return;
        setError(reason instanceof Error ? reason.message : "Unable to open communication workspace.");
      });
    return () => controller.abort();
  }, [contractId, status, user]);

  useEffect(() => {
    if (!selectedId || status !== "authenticated") return;
    const controller = new AbortController();
    void listMessages(selectedId, 0, 100, controller.signal)
      .then((items) => {
        if (controller.signal.aborted) return;
        setMessages(items);
        const through = items.at(-1)?.sequence ?? 0;
        latestSequence.current = through;
        if (through > 0) void markConversationRead(selectedId, through).catch(() => undefined);
        setError("");
      })
      .catch((reason: unknown) => {
        if (controller.signal.aborted) return;
        setError(reason instanceof Error ? reason.message : "Unable to load messages.");
      });
    return () => controller.abort();
  }, [selectedId, status]);

  useEffect(() => {
    if (!selectedId || status !== "authenticated" || realtime.state === "live") return;
    const interval = window.setInterval(() => {
      const after = latestSequence.current;
      void listMessages(selectedId, after, 100)
        .then((items) => {
          if (!items.length) return;
          setMessages((current) => mergeMessages(current, items));
          const through = items.at(-1)?.sequence ?? after;
          latestSequence.current = Math.max(latestSequence.current, through);
          if (through > 0) void markConversationRead(selectedId, through).catch(() => undefined);
        })
        .catch(() => undefined);
    }, 8000);
    return () => window.clearInterval(interval);
  }, [realtime.state, selectedId, status]);

  const selectedConversation = useMemo(
    () => conversations.find((item) => item.id === selectedId) ?? null,
    [conversations, selectedId],
  );

  const notificationEventTypes = useMemo(() => {
    const values = new Set<string>();
    for (const item of notifications) values.add(item.event_type);
    for (const preference of preferences) values.add(preference.event_type);
    return [...values].sort();
  }, [notifications, preferences]);

  async function submitMessage() {
    if (!selectedId || !user) return;
    const safeAttachmentIds = stagedFiles.filter((file) => file.status === "SAFE").map((file) => file.id);
    const normalized = body.trim();
    if (!normalized && !safeAttachmentIds.length) {
      setError("Write a message or attach at least one SAFE file before sending.");
      return;
    }
    if (!pendingClientMessageId.current) pendingClientMessageId.current = crypto.randomUUID();
    const clientMessageId = pendingClientMessageId.current;
    setBusy("send");
    setError("");
    setMessage("");
    try {
      let persisted: Message | null = null;
      try {
        persisted = await realtime.sendLive({
          clientMessageId,
          body: normalized,
          attachmentIds: safeAttachmentIds,
        });
      } catch {
        // A lost realtime ACK is safe to retry over REST with the identical client_message_id.
      }
      if (!persisted) {
        persisted = await sendMessage({
          conversationId: selectedId,
          clientMessageId,
          body: normalized,
          attachmentIds: safeAttachmentIds,
        });
      }
      pendingClientMessageId.current = "";
      latestSequence.current = Math.max(latestSequence.current, persisted.sequence);
      setMessages((current) => mergeMessages(current, [persisted]));
      setBody("");
      setStagedFiles([]);
      setMessage(`Message persisted as sequence ${persisted.sequence}.`);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Unable to send message.");
    } finally {
      setBusy("");
    }
  }

  async function stageAttachment(file: File) {
    setBusy("attachment");
    setError("");
    setMessage("");
    try {
      const reservation = await requestMessageUpload(file);
      const completed = await uploadReservedFile(reservation, file);
      setStagedFiles((current) => [
        ...current.filter((item) => item.id !== completed.id),
        { id: completed.id, original_name: completed.original_name, status: completed.status },
      ]);
      setMessage(
        completed.status === "SAFE"
          ? `${completed.original_name} is SAFE and ready to attach.`
          : `${completed.original_name} uploaded and is ${completed.status.toLowerCase()}; it will not be sent until SAFE.`,
      );
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Unable to upload attachment.");
    } finally {
      setBusy("");
    }
  }

  async function checkAttachment(file: StagedFile) {
    setBusy(`file:${file.id}`);
    setError("");
    try {
      const reservation = await getAttachmentDownload(file.id);
      setStagedFiles((current) =>
        current.map((item) => (item.id === file.id ? { ...item, status: "SAFE" } : item)),
      );
      setMessage(`${reservation.file.original_name} passed safety scanning and is ready to send.`);
    } catch (reason) {
      setError(
        reason instanceof Error
          ? reason.message
          : "The file is not available yet; it may still be scanning.",
      );
    } finally {
      setBusy("");
    }
  }

  async function openAttachment(fileId: string) {
    setError("");
    try {
      const reservation = await getAttachmentDownload(fileId);
      window.open(reservation.download_url, "_blank", "noopener,noreferrer");
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Attachment is unavailable.");
    }
  }

  async function readNotification(item: NotificationItem) {
    if (item.read_at) return;
    setBusy(`notification:${item.id}`);
    setError("");
    try {
      const updated = await markNotificationRead(item.id);
      setNotifications((current) => current.map((value) => (value.id === item.id ? updated : value)));
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Unable to mark notification read.");
    } finally {
      setBusy("");
    }
  }

  function preferenceFor(eventType: string, channel: string): NotificationPreference {
    return (
      preferences.find(
        (preference) => preference.event_type === eventType && preference.channel === channel,
      ) ?? { event_type: eventType, channel, enabled: channel === "IN_APP" }
    );
  }

  async function togglePreference(eventType: string, channel: string) {
    const current = preferenceFor(eventType, channel);
    const next = { ...current, enabled: !current.enabled };
    setBusy(`preference:${eventType}:${channel}`);
    setError("");
    try {
      const saved = await setNotificationPreference(next);
      setPreferences((items) => [
        ...items.filter(
          (item) => !(item.event_type === saved.event_type && item.channel === saved.channel),
        ),
        saved,
      ]);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Unable to update notification preference.");
    } finally {
      setBusy("");
    }
  }

  if (status === "loading") {
    return <main className={styles.page}><p className={styles.empty}>Opening communication workspace…</p></main>;
  }
  if (!user) return null;

  return (
    <main className={styles.page}>
      <section className={styles.hero}>
        <div>
          <span className={styles.eyebrow}>Communication</span>
          <h1>Messages that persist before they appear.</h1>
          <p>
            Contract chat uses backend sequence ordering and idempotent client message IDs. Live transport accelerates delivery; PostgreSQL remains the record of truth.
          </p>
        </div>
        <aside>
          <strong>Safe by construction</strong>
          <p>Attachments stay out of message payloads until the backend marks them SAFE. Reconnects recover from server cursors rather than local guesses.</p>
        </aside>
      </section>

      {error ? <p className={styles.errorBanner} role="alert">{error}</p> : null}
      {message ? <p className={styles.banner} role="status">{message}</p> : null}

      <section className={styles.workspace} aria-label="Contract messages">
        <aside className={styles.sidebar}>
          <div className={styles.heading}>
            <div>
              <span className={styles.eyebrow}>Inbox</span>
              <h2>Conversations</h2>
            </div>
          </div>
          {conversations.length ? (
            <ul className={styles.conversationList}>
              {conversations.map((conversation) => (
                <li key={conversation.id}>
                  <button
                    type="button"
                    className={styles.conversationButton}
                    aria-current={conversation.id === selectedId}
                    onClick={() => setSelectedId(conversation.id)}
                  >
                    <strong>{conversationLabel(conversation, user.id)}</strong>
                    <span>Next sequence {conversation.next_sequence}</span>
                  </button>
                </li>
              ))}
            </ul>
          ) : (
            <p className={styles.empty}>No contract conversations yet. Open a signed contract to start its private thread.</p>
          )}
        </aside>

        <div className={styles.thread}>
          <header className={styles.threadHeader}>
            <div className={styles.heading}>
              <div>
                <span className={styles.eyebrow}>Server ordered</span>
                <h3>{selectedConversation ? conversationLabel(selectedConversation, user.id) : "Select a conversation"}</h3>
                {selectedConversation?.contract_id ? <p className={styles.threadMeta}>Contract {selectedConversation.contract_id.slice(0, 12)}…</p> : null}
                {realtime.state === "live" && realtime.peerOnline !== null ? (
                  <p className={styles.threadMeta}>{realtime.peerOnline ? "Other party online" : "Other party currently offline"}</p>
                ) : null}
              </div>
              <span className={styles.connectionState} data-state={realtime.state}>
                {realtime.state === "live" ? "Live" : realtime.state === "connecting" ? "Connecting" : "Cursor sync"}
              </span>
            </div>
          </header>

          <div className={styles.messageScroller}>
            {selectedId && messages.length ? (
              <ol className={styles.messageList} aria-label="Messages">
                {messages.map((item) => (
                  <li className={styles.message} data-own={item.sender_user_id === user.id} key={item.id}>
                    {item.body ? <p>{item.body}</p> : null}
                    {item.attachments.length ? (
                      <div className={styles.attachmentList}>
                        {item.attachments.map((fileId) => (
                          <button className={styles.attachmentButton} type="button" key={fileId} onClick={() => void openAttachment(fileId)}>
                            Attachment {fileId.slice(0, 8)}…
                          </button>
                        ))}
                      </div>
                    ) : null}
                    <footer>
                      <span>{formatDateTime(item.created_at)}</span>
                      <span>{receiptLabel(item, user.id)}</span>
                    </footer>
                  </li>
                ))}
              </ol>
            ) : (
              <p className={styles.empty}>{selectedId ? "No messages yet. Start the contract conversation." : "Choose a conversation to view its persisted history."}</p>
            )}
          </div>

          <div className={styles.composer}>
            <label htmlFor="message-body" className={styles.eyebrow}>Message</label>
            <textarea
              id="message-body"
              value={body}
              maxLength={8000}
              disabled={!selectedId || busy === "send"}
              onChange={(event) => setBody(event.target.value)}
              placeholder="Write a contract message…"
            />
            <p className={styles.composerHint}>Retries preserve the same client message ID until the backend confirms persistence.</p>

            {stagedFiles.length ? (
              <ul className={styles.pendingFiles}>
                {stagedFiles.map((file) => (
                  <li key={file.id}>
                    <div><strong>{file.original_name}</strong><br /><small>{file.status}</small></div>
                    {file.status !== "SAFE" ? (
                      <button className={styles.attachmentButton} type="button" disabled={busy === `file:${file.id}`} onClick={() => void checkAttachment(file)}>
                        {busy === `file:${file.id}` ? "Checking…" : "Check safety status"}
                      </button>
                    ) : null}
                  </li>
                ))}
              </ul>
            ) : null}

            <div className={styles.composerActions}>
              <div>
                <input
                  className={styles.fileInput}
                  type="file"
                  aria-label="Attach file"
                  accept=".pdf,.jpg,.jpeg,.png,.txt,application/pdf,image/jpeg,image/png,text/plain"
                  disabled={!selectedId || busy === "attachment"}
                  onChange={(event) => {
                    const file = event.target.files?.[0];
                    if (file) void stageAttachment(file);
                    event.currentTarget.value = "";
                  }}
                />
              </div>
              <button className={styles.primaryButton} type="button" disabled={!selectedId || busy === "send"} onClick={() => void submitMessage()}>
                {busy === "send" ? "Persisting…" : "Send message"}
              </button>
            </div>
          </div>
        </div>
      </section>

      <section className={styles.notificationsPanel} aria-labelledby="notifications-heading">
        <div className={styles.heading}>
          <div>
            <span className={styles.eyebrow}>Notifications</span>
            <h2 id="notifications-heading">Inbox & preferences</h2>
          </div>
          <p>In-app notifications are persisted and deduplicated by the backend. Preferences only change channels for a specific event type.</p>
        </div>

        <div className={styles.notificationsLayout}>
          <div>
            {notifications.length ? (
              <ul className={styles.notificationList}>
                {[...notifications].reverse().map((item) => (
                  <li className={styles.notificationItem} data-unread={!item.read_at} key={item.id}>
                    <strong>{item.title}</strong>
                    <p>{item.body}</p>
                    <div className={styles.notificationMeta}>
                      <span>{item.event_type}</span>
                      <span>{formatDateTime(item.created_at)}</span>
                      <span>{item.read_at ? "Read" : "Unread"}</span>
                    </div>
                    {!item.read_at ? (
                      <button className={styles.notificationButton} type="button" disabled={busy === `notification:${item.id}`} onClick={() => void readNotification(item)}>
                        {busy === `notification:${item.id}` ? "Saving…" : "Mark read"}
                      </button>
                    ) : null}
                  </li>
                ))}
              </ul>
            ) : <p className={styles.empty}>No notifications yet.</p>}
          </div>

          <aside>
            <div className={styles.heading}><div><span className={styles.eyebrow}>Channels</span><h3>Delivery preferences</h3></div></div>
            {notificationEventTypes.length ? (
              <ul className={styles.preferenceGrid}>
                {notificationEventTypes.map((eventType) => (
                  <li className={styles.preferenceRow} key={eventType}>
                    <strong>{eventType}</strong>
                    <div className={styles.preferenceChannels}>
                      {NOTIFICATION_CHANNELS.map((channel) => {
                        const preference = preferenceFor(eventType, channel);
                        const key = `preference:${eventType}:${channel}`;
                        return (
                          <button
                            className={styles.preferenceToggle}
                            type="button"
                            data-enabled={preference.enabled}
                            disabled={busy === key}
                            key={channel}
                            onClick={() => void togglePreference(eventType, channel)}
                          >
                            {channel} · {preference.enabled ? "on" : "off"}
                          </button>
                        );
                      })}
                    </div>
                  </li>
                ))}
              </ul>
            ) : <p className={styles.empty}>Preferences appear when an event type has been observed or explicitly configured.</p>}
          </aside>
        </div>
      </section>
    </main>
  );
}
