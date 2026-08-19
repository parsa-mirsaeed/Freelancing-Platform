import { NextResponse } from "next/server";

import { applySessionCookies, clearSessionCookies } from "@/lib/server/auth-session";
import { backendWithSession } from "@/lib/server/session-backend";

export async function GET(): Promise<NextResponse> {
  const { response: upstream, rotated } = await backendWithSession("/api/v1/auth/me");
  const payload: unknown = await upstream.json().catch(() => ({}));
  const response = NextResponse.json(payload, { status: upstream.status });
  if (rotated) applySessionCookies(response, rotated);
  if (upstream.status === 401) clearSessionCookies(response);
  return response;
}
