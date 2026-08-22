import "server-only";

import { backendFetch } from "@/lib/server/backend";
import { readSessionTokens, type SessionTokens } from "@/lib/server/auth-session";

interface SessionBackendResult {
  response: Response;
  rotated?: SessionTokens;
}

function isSessionTokens(value: unknown): value is SessionTokens {
  if (!value || typeof value !== "object") return false;
  const token = value as Partial<SessionTokens>;
  return typeof token.access_token === "string" && typeof token.refresh_token === "string" && token.token_type === "Bearer";
}

async function refreshSession(refreshToken: string): Promise<SessionTokens | undefined> {
  const response = await backendFetch("/api/v1/auth/refresh", {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({ refresh_token: refreshToken }),
  });
  if (!response.ok) return undefined;
  const payload: unknown = await response.json();
  return isSessionTokens(payload) ? payload : undefined;
}

function withBearer(init: RequestInit, access?: string): RequestInit {
  const headers = new Headers(init.headers);
  if (access) headers.set("authorization", `Bearer ${access}`);
  return { ...init, headers };
}

export async function backendWithSession(path: string, init: RequestInit = {}): Promise<SessionBackendResult> {
  const session = await readSessionTokens();
  let response = await backendFetch(path, withBearer(init, session.access));
  if (response.status !== 401 || !session.refresh) return { response };

  const rotated = await refreshSession(session.refresh);
  if (!rotated) return { response };
  response = await backendFetch(path, withBearer(init, rotated.access_token));
  return { response, rotated };
}
