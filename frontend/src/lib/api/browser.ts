export class BrowserApiError extends Error {
  constructor(
    message: string,
    public readonly status: number,
    public readonly code?: string,
  ) {
    super(message);
    this.name = "BrowserApiError";
  }
}

export async function browserApi<T>(path: string, init: RequestInit = {}): Promise<T> {
  const normalized = path.replace(/^\/+/, "");
  if (!normalized || normalized.includes("..")) {
    throw new TypeError("Invalid browser API path.");
  }

  const headers = new Headers(init.headers);
  if (init.body && !headers.has("content-type")) headers.set("content-type", "application/json");
  headers.set("accept", "application/json");

  const response = await fetch(`/api/backend/${normalized}`, {
    ...init,
    headers,
    credentials: "same-origin",
  });
  if (response.status === 204) return undefined as T;

  const contentType = response.headers.get("content-type") ?? "";
  const payload = contentType.includes("application/json") ? await response.json() : null;
  if (!response.ok) {
    const error = payload && typeof payload === "object" && "error" in payload
      ? (payload as { error?: { message?: string; code?: string } }).error
      : undefined;
    throw new BrowserApiError(error?.message ?? `Request failed with status ${response.status}.`, response.status, error?.code);
  }
  return payload as T;
}
