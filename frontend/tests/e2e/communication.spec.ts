import { expect, test, type Page } from "@playwright/test";

const freelancerId = "11111111-1111-4111-8111-111111111111";
const employerId = "a2111111-1111-4111-8111-111111111111";
const contractId = "d2111111-1111-4111-8111-111111111111";
const conversationId = "e2111111-1111-4111-8111-111111111111";

function conversation() {
  return {
    id: conversationId,
    contract_id: contractId,
    next_sequence: 2,
    created_at: "2026-08-22T12:00:00Z",
    members: [
      { user_id: freelancerId, last_read_sequence: 1, joined_at: "2026-08-22T12:00:00Z" },
      { user_id: employerId, last_read_sequence: 0, joined_at: "2026-08-22T12:00:00Z" },
    ],
  };
}

function existingMessage() {
  return {
    id: "f2111111-1111-4111-8111-111111111111",
    conversation_id: conversationId,
    sender_user_id: employerId,
    sequence: 1,
    client_message_id: "existing-message",
    body: "I added the latest contract context.",
    attachments: [],
    receipts: [],
    created_at: "2026-08-22T12:05:00Z",
  };
}

async function signIn(page: Page) {
  await page.goto("/login?next=/dashboard/messages");
  await page.getByLabel("Email address").fill("freelancer@example.com");
  await page.getByLabel("Password").fill("correct-horse-battery-staple");
  await page.getByRole("button", { name: "Sign in securely" }).click();
  await expect(page).toHaveURL(/\/dashboard\/messages$/);
}

async function routeWorkspaceDefaults(page: Page) {
  await page.route("**/api/backend/conversations", (route) =>
    route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify([conversation()]) }),
  );
  await page.route(`**/api/backend/conversations/${conversationId}/messages?*`, (route) =>
    route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify([existingMessage()]) }),
  );
  await page.route(`**/api/backend/conversations/${conversationId}/read`, (route) =>
    route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ through_sequence: 1 }) }),
  );
  await page.route("**/api/backend/notifications?*", (route) =>
    route.fulfill({ status: 200, contentType: "application/json", body: "[]" }),
  );
  await page.route("**/api/backend/notifications/preferences", (route) =>
    route.fulfill({ status: 200, contentType: "application/json", body: "[]" }),
  );
}

test("persisted message send keeps a stable client message id and renders server sequence", async ({ page }) => {
  await routeWorkspaceDefaults(page);
  let capturedClientMessageId = "";
  await page.route(`**/api/backend/conversations/${conversationId}/messages`, async (route) => {
    const input = route.request().postDataJSON();
    capturedClientMessageId = input.client_message_id;
    expect(capturedClientMessageId).toBeTruthy();
    expect(input).toEqual({
      client_message_id: capturedClientMessageId,
      body: "The delivery evidence is ready for review.",
      attachment_ids: [],
    });
    await route.fulfill({
      status: 201,
      contentType: "application/json",
      body: JSON.stringify({
        id: "f3111111-1111-4111-8111-111111111111",
        conversation_id: conversationId,
        sender_user_id: freelancerId,
        sequence: 2,
        client_message_id: capturedClientMessageId,
        body: "The delivery evidence is ready for review.",
        attachments: [],
        receipts: [],
        created_at: "2026-08-22T12:10:00Z",
      }),
    });
  });

  await signIn(page);
  const workspace = page.getByRole("region", { name: "Contract messages" });
  await expect(workspace.getByText("I added the latest contract context.")).toBeVisible({ timeout: 15_000 });
  await expect(workspace.getByText("Cursor sync", { exact: true })).toBeVisible({ timeout: 15_000 });

  await workspace.getByRole("textbox", { name: "Message" }).fill("The delivery evidence is ready for review.");
  await workspace.getByRole("button", { name: "Send message" }).click();

  await expect(page.getByText("Message persisted as sequence 2.")).toBeVisible();
  await expect(workspace.getByText("The delivery evidence is ready for review.")).toBeVisible();
  await expect(workspace.getByText("Persisted", { exact: true })).toBeVisible();
});

test("notification read state and channel preference follow backend confirmations", async ({ page }) => {
  await page.route("**/api/backend/conversations", (route) =>
    route.fulfill({ status: 200, contentType: "application/json", body: "[]" }),
  );
  await page.route("**/api/backend/notifications?*", (route) =>
    route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify([
        {
          id: "aa111111-1111-4111-8111-111111111111",
          event_type: "message.created",
          title: "New contract message",
          body: "A new message was persisted in your contract conversation.",
          payload: { conversation_id: conversationId },
          dedupe_key: "message:1:freelancer",
          read_at: null,
          created_at: "2026-08-22T12:12:00Z",
          deliveries: [{ channel: "IN_APP", status: "DELIVERED", attempt_count: 0 }],
        },
      ]),
    }),
  );
  await page.route("**/api/backend/notifications/preferences", async (route) => {
    if (route.request().method() === "PUT") {
      const input = route.request().postDataJSON();
      expect(input).toEqual({ event_type: "message.created", channel: "EMAIL", enabled: false });
      return route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(input) });
    }
    return route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify([{ event_type: "message.created", channel: "EMAIL", enabled: true }]),
    });
  });
  await page.route("**/api/backend/notifications/aa111111-1111-4111-8111-111111111111/read", (route) =>
    route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        id: "aa111111-1111-4111-8111-111111111111",
        event_type: "message.created",
        title: "New contract message",
        body: "A new message was persisted in your contract conversation.",
        payload: { conversation_id: conversationId },
        dedupe_key: "message:1:freelancer",
        read_at: "2026-08-22T12:13:00Z",
        created_at: "2026-08-22T12:12:00Z",
        deliveries: [{ channel: "IN_APP", status: "DELIVERED", attempt_count: 0 }],
      }),
    }),
  );

  await signIn(page);
  await expect(page.getByText("New contract message")).toBeVisible({ timeout: 15_000 });
  await page.getByRole("button", { name: "Mark read" }).click();
  await expect(page.getByText("Read", { exact: true })).toBeVisible();
  await expect(page.getByRole("button", { name: "Mark read" })).toHaveCount(0);

  await page.getByRole("button", { name: "EMAIL · on" }).click();
  await expect(page.getByRole("button", { name: "EMAIL · off" })).toBeVisible();
});

test("scanning attachment is never placed in the send payload", async ({ page }) => {
  await routeWorkspaceDefaults(page);
  let sendCalls = 0;
  await page.route(`**/api/backend/conversations/${conversationId}/messages`, (route) => {
    sendCalls += 1;
    return route.fulfill({ status: 500, contentType: "application/json", body: "{}" });
  });
  await page.route("**/api/backend/files/uploads", async (route) => {
    expect(route.request().postDataJSON()).toMatchObject({
      original_name: "evidence.txt",
      mime_type: "text/plain",
      purpose: "MESSAGE_ATTACHMENT",
    });
    await route.fulfill({
      status: 201,
      contentType: "application/json",
      body: JSON.stringify({
        file: {
          id: "bb111111-1111-4111-8111-111111111111",
          original_name: "evidence.txt",
          mime_type: "text/plain",
          size_bytes: 8,
          sha256: null,
          purpose: "MESSAGE_ATTACHMENT",
          status: "QUARANTINED",
          rejection_reason: null,
          created_at: "2026-08-22T12:14:00Z",
        },
        upload_url: "http://127.0.0.1:3000/mock-upload-target",
      }),
    });
  });
  await page.route("**/mock-upload-target", (route) => route.fulfill({ status: 200, body: "" }));
  await page.route("**/api/backend/files/bb111111-1111-4111-8111-111111111111/complete", (route) =>
    route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        id: "bb111111-1111-4111-8111-111111111111",
        original_name: "evidence.txt",
        mime_type: "text/plain",
        size_bytes: 8,
        sha256: null,
        purpose: "MESSAGE_ATTACHMENT",
        status: "SCANNING",
        rejection_reason: null,
        created_at: "2026-08-22T12:14:00Z",
      }),
    }),
  );

  await signIn(page);
  await page.getByLabel("Attach file").setInputFiles({
    name: "evidence.txt",
    mimeType: "text/plain",
    buffer: Buffer.from("evidence"),
  });
  await expect(page.getByText(/uploaded and is scanning/i)).toBeVisible();
  await expect(page.getByText("SCANNING", { exact: true })).toBeVisible();

  await page.getByRole("button", { name: "Send message" }).click();
  await expect(page.getByText("Write a message or attach at least one SAFE file before sending.")).toBeVisible();
  expect(sendCalls).toBe(0);
});
