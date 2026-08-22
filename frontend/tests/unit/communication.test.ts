import { beforeEach, describe, expect, it, vi } from "vitest";

import {
  markConversationRead,
  openProjectConversation,
  requestMessageUpload,
  requestRealtimeTicket,
  sendMessage,
  setNotificationPreference,
} from "@/lib/api/communication";

vi.mock("@/lib/api/product-client", () => ({
  productJson: vi.fn(async () => ({ ok: true })),
}));

import { productJson } from "@/lib/api/product-client";

describe("communication API contract", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("preserves caller-owned message idempotency and SAFE attachment references", async () => {
    await sendMessage({
      conversationId: "conversation-1",
      clientMessageId: "client-message-stable",
      body: "Persist before acknowledgement",
      attachmentIds: ["file-safe-1", "file-safe-2"],
    });

    expect(productJson).toHaveBeenLastCalledWith("conversations/conversation-1/messages", {
      method: "POST",
      body: JSON.stringify({
        client_message_id: "client-message-stable",
        body: "Persist before acknowledgement",
        attachment_ids: ["file-safe-1", "file-safe-2"],
      }),
    });
  });

  it("reserves message uploads only for MESSAGE_ATTACHMENT purpose", async () => {
    const file = new File(["evidence"], "evidence.txt", { type: "text/plain" });
    await requestMessageUpload(file);
    expect(productJson).toHaveBeenLastCalledWith("files/uploads", {
      method: "POST",
      body: JSON.stringify({
        original_name: "evidence.txt",
        mime_type: "text/plain",
        size_bytes: 8,
        purpose: "MESSAGE_ATTACHMENT",
      }),
    });
  });

  it("requests a realtime-only ticket through the authenticated BFF path", async () => {
    await requestRealtimeTicket();
    expect(productJson).toHaveBeenLastCalledWith("auth/realtime-ticket", { method: "POST" });
  });

  it("resolves a project to its contract before opening the single contract conversation", async () => {
    vi.mocked(productJson)
      .mockResolvedValueOnce({ id: "contract-7" })
      .mockResolvedValueOnce({ id: "conversation-9" });
    await openProjectConversation("project-3");
    expect(productJson).toHaveBeenNthCalledWith(1, "projects/project-3/contract");
    expect(productJson).toHaveBeenNthCalledWith(2, "contracts/contract-7/conversation", {
      method: "POST",
    });
  });

  it("advances read cursors and preferences through backend-authoritative writes", async () => {
    await markConversationRead("conversation-1", 14);
    expect(productJson).toHaveBeenLastCalledWith("conversations/conversation-1/read", {
      method: "POST",
      body: JSON.stringify({ through_sequence: 14 }),
    });

    await setNotificationPreference({
      event_type: "message.created",
      channel: "EMAIL",
      enabled: false,
    });
    expect(productJson).toHaveBeenLastCalledWith("notifications/preferences", {
      method: "PUT",
      body: JSON.stringify({
        event_type: "message.created",
        channel: "EMAIL",
        enabled: false,
      }),
    });
  });
});
