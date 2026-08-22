import { expect, test, type Page } from "@playwright/test";

import type { CallSession } from "@/lib/api/calls";
import type { Conversation } from "@/lib/api/communication";

const userId = "11111111-1111-4111-8111-111111111111";
const peerId = "22222222-2222-4222-8222-222222222222";
const conversationId = "33333333-3333-4333-8333-333333333333";

const conversation: Conversation = {
  id: conversationId,
  contract_id: "44444444-4444-4444-8444-444444444444",
  next_sequence: 1,
  created_at: "2026-08-22T18:00:00Z",
  members: [
    { user_id: userId, last_read_sequence: 0, joined_at: "2026-08-22T18:00:00Z" },
    { user_id: peerId, last_read_sequence: 0, joined_at: "2026-08-22T18:00:00Z" },
  ],
};

async function routeWorkspace(page: Page, liveCall: CallSession | null) {
  await page.route("**/api/session/me", (route) =>
    route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ id: userId, email: "caller@example.com", roles: ["employer"] }),
    }),
  );
  await page.route("**/api/backend/conversations", (route) =>
    route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify([conversation]) }),
  );
  await page.route(`**/api/backend/conversations/${conversationId}/call`, (route) =>
    route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ call: liveCall }),
    }),
  );
}

test("calls workspace refuses to fake media when realtime signaling is unavailable", async ({ page }) => {
  await routeWorkspace(page, null);
  await page.goto("/dashboard/calls");

  await expect(page.getByRole("heading", { level: 1, name: "Voice and video stay peer to peer." })).toBeVisible();
  await expect(page.getByText("Signaling offline", { exact: true })).toBeVisible();
  await expect(page.getByRole("button", { name: "Start voice call" })).toBeDisabled();
  await expect(page.getByRole("button", { name: "Start video call" })).toBeDisabled();
});

test("calls workspace recovers an invited call without persisting SDP or ICE", async ({ page }) => {
  const invited: CallSession = {
    id: "55555555-5555-4555-8555-555555555555",
    conversation_id: conversationId,
    caller_user_id: peerId,
    callee_user_id: userId,
    client_call_id: "recover-invite-1",
    call_type: "VIDEO",
    status: "INVITED",
    created_at: "2026-08-22T18:05:00Z",
    accepted_at: null,
    ended_at: null,
    ended_by_user_id: null,
    end_reason: null,
  };
  await routeWorkspace(page, invited);
  await page.goto("/dashboard/calls");

  await expect(page.getByText("Incoming call", { exact: true }).first()).toBeVisible();
  await expect(page.getByRole("button", { name: "Accept video call" })).toBeDisabled();
  await expect(page.getByRole("button", { name: "Decline" })).toBeDisabled();
  await expect(page.getByRole("button", { name: "End call" })).toBeDisabled();
});
