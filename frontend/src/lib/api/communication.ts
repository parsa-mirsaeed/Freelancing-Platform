import { productJson } from "@/lib/api/product-client";

export interface ConversationMember {
  user_id: string;
  last_read_sequence: number;
  joined_at: string;
}

export interface Conversation {
  id: string;
  contract_id: string | null;
  next_sequence: number;
  members: ConversationMember[];
  created_at: string;
}

export interface MessageReceipt {
  user_id: string;
  type: "DELIVERED" | "READ" | string;
  created_at: string;
}

export interface Message {
  id: string;
  conversation_id: string;
  sender_user_id: string;
  sequence: number;
  client_message_id: string;
  body: string;
  attachments: string[];
  receipts: MessageReceipt[];
  created_at: string;
}

export interface RealtimeTicket {
  token: string;
  token_type: "Realtime";
  expires_at: string;
}

export interface FileObject {
  id: string;
  original_name: string;
  mime_type: string;
  size_bytes: number;
  sha256: string | null;
  purpose: string;
  status: "QUARANTINED" | "SCANNING" | "SAFE" | "REJECTED" | string;
  rejection_reason: string | null;
  created_at: string;
}

export interface UploadReservation {
  file: FileObject;
  upload_url: string;
}

export interface DownloadReservation {
  file: FileObject;
  download_url: string;
}

export interface NotificationDelivery {
  channel: string;
  status: string;
  attempt_count: number;
}

export interface NotificationItem {
  id: string;
  event_type: string;
  title: string;
  body: string;
  payload: Record<string, unknown>;
  dedupe_key: string;
  read_at: string | null;
  created_at: string;
  deliveries: NotificationDelivery[];
}

export interface NotificationPreference {
  event_type: string;
  channel: "IN_APP" | "EMAIL" | "PUSH" | "SMS" | string;
  enabled: boolean;
}

export function listConversations(signal?: AbortSignal): Promise<Conversation[]> {
  return productJson<Conversation[]>("conversations", { signal });
}

export function openContractConversation(contractId: string): Promise<Conversation> {
  return productJson<Conversation>(`contracts/${contractId}/conversation`, { method: "POST" });
}

export function listMessages(
  conversationId: string,
  after = 0,
  limit = 100,
  signal?: AbortSignal,
): Promise<Message[]> {
  const query = new URLSearchParams({ after: String(after), limit: String(limit) });
  return productJson<Message[]>(`conversations/${conversationId}/messages?${query}`, { signal });
}

export function sendMessage({
  conversationId,
  clientMessageId,
  body,
  attachmentIds,
}: {
  conversationId: string;
  clientMessageId: string;
  body: string;
  attachmentIds: string[];
}): Promise<Message> {
  return productJson<Message>(`conversations/${conversationId}/messages`, {
    method: "POST",
    body: JSON.stringify({
      client_message_id: clientMessageId,
      body,
      attachment_ids: attachmentIds,
    }),
  });
}

export function markConversationDelivered(
  conversationId: string,
  throughSequence: number,
): Promise<{ through_sequence: number }> {
  return productJson<{ through_sequence: number }>(`conversations/${conversationId}/delivered`, {
    method: "POST",
    body: JSON.stringify({ through_sequence: throughSequence }),
  });
}

export function markConversationRead(
  conversationId: string,
  throughSequence: number,
): Promise<{ through_sequence: number }> {
  return productJson<{ through_sequence: number }>(`conversations/${conversationId}/read`, {
    method: "POST",
    body: JSON.stringify({ through_sequence: throughSequence }),
  });
}

export function requestRealtimeTicket(): Promise<RealtimeTicket> {
  return productJson<RealtimeTicket>("auth/realtime-ticket", { method: "POST" });
}

export function requestMessageUpload(file: File): Promise<UploadReservation> {
  return productJson<UploadReservation>("files/uploads", {
    method: "POST",
    body: JSON.stringify({
      original_name: file.name,
      mime_type: file.type,
      size_bytes: file.size,
      purpose: "MESSAGE_ATTACHMENT",
    }),
  });
}

export async function uploadReservedFile(
  reservation: UploadReservation,
  file: File,
): Promise<FileObject> {
  const uploaded = await fetch(reservation.upload_url, {
    method: "PUT",
    headers: { "Content-Type": file.type },
    body: file,
  });
  if (!uploaded.ok) throw new Error(`Object upload failed with ${uploaded.status}.`);
  return productJson<FileObject>(`files/${reservation.file.id}/complete`, { method: "POST" });
}

export function getAttachmentDownload(fileId: string): Promise<DownloadReservation> {
  return productJson<DownloadReservation>(`files/${fileId}`);
}

export function listNotifications(signal?: AbortSignal): Promise<NotificationItem[]> {
  return productJson<NotificationItem[]>("notifications?limit=100", { signal });
}

export function markNotificationRead(notificationId: string): Promise<NotificationItem> {
  return productJson<NotificationItem>(`notifications/${notificationId}/read`, { method: "POST" });
}

export function listNotificationPreferences(signal?: AbortSignal): Promise<NotificationPreference[]> {
  return productJson<NotificationPreference[]>("notifications/preferences", { signal });
}

export function setNotificationPreference(preference: NotificationPreference): Promise<NotificationPreference> {
  return productJson<NotificationPreference>("notifications/preferences", {
    method: "PUT",
    body: JSON.stringify({
      event_type: preference.event_type,
      channel: preference.channel,
      enabled: preference.enabled,
    }),
  });
}
