import { NextResponse } from "next/server";

import { isTokenEnvelope } from "@/lib/api/types";
import { backendFetch } from "@/lib/server/backend";
import { applySessionCookies } from "@/lib/server/auth-session";

export async function POST(request: Request): Promise<NextResponse> {
  const upstream = await backendFetch("/api/v1/auth/register", {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: await request.text(),
  });
  const payload: unknown = await upstream.json().catch(() => ({}));
  if (!upstream.ok || !isTokenEnvelope(payload)) {
    return NextResponse.json(payload, { status: upstream.status });
  }
  const response = NextResponse.json({ user: payload.user }, { status: 201 });
  applySessionCookies(response, payload);
  return response;
}
