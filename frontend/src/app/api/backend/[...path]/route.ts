import { NextResponse } from "next/server";

import { applySessionCookies, clearSessionCookies } from "@/lib/server/auth-session";
import { forwardedRequestHeaders, isProxyPathAllowed } from "@/lib/server/proxy-policy";
import { backendWithSession } from "@/lib/server/session-backend";

type Context = { params: Promise<{ path: string[] }> };

async function proxy(request: Request, context: Context): Promise<NextResponse> {
  const { path } = await context.params;
  if (!isProxyPathAllowed(path)) {
    return NextResponse.json({ error: { code: "proxy_path_blocked", message: "Route is not available through the browser proxy." } }, { status: 404 });
  }

  const method = request.method.toUpperCase();
  const init: RequestInit = {
    method,
    headers: forwardedRequestHeaders(request),
  };
  if (!new Set(["GET", "HEAD"]).has(method)) {
    init.body = await request.arrayBuffer();
  }

  const { response: upstream, rotated } = await backendWithSession(`/api/v1/${path.join("/")}`, init);
  const headers = new Headers();
  for (const name of ["content-type", "content-disposition"] as const) {
    const value = upstream.headers.get(name);
    if (value) headers.set(name, value);
  }
  const response = new NextResponse(await upstream.arrayBuffer(), { status: upstream.status, headers });
  if (rotated) applySessionCookies(response, rotated);
  if (upstream.status === 401) clearSessionCookies(response);
  return response;
}

export const GET = proxy;
export const POST = proxy;
export const PUT = proxy;
export const PATCH = proxy;
export const DELETE = proxy;
