import "server-only";

const DEFAULT_BACKEND = "http://127.0.0.1:8000";

function backendOrigin(): string {
  const configured = process.env.BACKEND_API_URL ?? DEFAULT_BACKEND;
  const url = new URL(configured);
  if (!/^https?:$/.test(url.protocol)) {
    throw new Error("BACKEND_API_URL must use http or https");
  }
  return url.origin;
}

export async function backendFetch(path: string, init: RequestInit = {}): Promise<Response> {
  if (!path.startsWith("/api/v1/")) {
    throw new Error("Backend path must be rooted at /api/v1/");
  }
  const headers = new Headers(init.headers);
  if (!headers.has("accept")) headers.set("accept", "application/json");

  return fetch(new URL(path, backendOrigin()), {
    ...init,
    headers,
    cache: "no-store",
    signal: init.signal ?? AbortSignal.timeout(12_000),
  });
}
