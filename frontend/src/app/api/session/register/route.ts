import { NextResponse } from "next/server";

import { isTokenEnvelope } from "@/lib/api/types";
import {
  applyDeviceCookie,
  applySessionCookies,
  readDeviceId,
} from "@/lib/server/auth-session";
import { backendFetch } from "@/lib/server/backend";

export async function POST(request: Request): Promise<NextResponse> {
  const existingDeviceId = await readDeviceId();
  const deviceId = existingDeviceId ?? crypto.randomUUID();
  const upstream = await backendFetch("/api/v1/auth/register", {
    method: "POST",
    headers: {
      "content-type": "application/json",
      "user-agent": request.headers.get("user-agent") ?? "",
      "x-device-id": deviceId,
    },
    body: await request.text(),
  });
  const payload: unknown = await upstream.json().catch(() => ({}));
  if (!upstream.ok || !isTokenEnvelope(payload)) {
    return NextResponse.json(payload, { status: upstream.status });
  }
  const response = NextResponse.json({ user: payload.user }, { status: 201 });
  applySessionCookies(response, payload);
  if (!existingDeviceId) applyDeviceCookie(response, deviceId);
  return response;
}
