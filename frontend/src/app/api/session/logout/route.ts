import { NextResponse } from "next/server";

import { clearSessionCookies } from "@/lib/server/auth-session";
import { backendWithSession } from "@/lib/server/session-backend";

export async function POST(): Promise<NextResponse> {
  await backendWithSession("/api/v1/auth/logout", { method: "POST" }).catch(() => undefined);
  const response = new NextResponse(null, { status: 204 });
  clearSessionCookies(response);
  return response;
}
