const BLOCKED_PREFIXES = [
  "auth/login",
  "auth/register",
  "auth/refresh",
  "payments/webhooks/",
];

export function isProxyPathAllowed(parts: readonly string[]): boolean {
  if (parts.length === 0 || parts.some((part) => !part || part === "." || part === "..")) return false;
  const path = parts.join("/");
  return !BLOCKED_PREFIXES.some((prefix) => path === prefix || path.startsWith(prefix));
}

export function forwardedRequestHeaders(request: Request): Headers {
  const headers = new Headers();
  for (const name of ["content-type", "idempotency-key"]) {
    const value = request.headers.get(name);
    if (value) headers.set(name, value);
  }
  return headers;
}
