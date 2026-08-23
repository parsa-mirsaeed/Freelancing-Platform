export type UserRole = "freelancer" | "employer" | "admin" | string;

export interface SessionUser {
  id: string;
  email: string;
  roles: UserRole[];
  mfa_enabled?: boolean;
}

export interface TokenEnvelope {
  user: SessionUser;
  access_token: string;
  refresh_token: string;
  token_type: "Bearer";
}

export interface ApiErrorPayload {
  type?: string;
  title?: string;
  status?: number;
  detail?: string;
  request_id?: string | null;
  error?: {
    code?: string;
    message?: string;
    request_id?: string;
  };
  message?: string;
}

export function apiErrorMessage(payload: unknown, fallback = "Something went wrong."): string {
  if (!payload || typeof payload !== "object") return fallback;
  const candidate = payload as ApiErrorPayload;
  return candidate.error?.message ?? candidate.detail ?? candidate.message ?? fallback;
}

export function isTokenEnvelope(value: unknown): value is TokenEnvelope {
  if (!value || typeof value !== "object") return false;
  const token = value as Partial<TokenEnvelope>;
  return Boolean(
    token.user &&
      typeof token.access_token === "string" &&
      typeof token.refresh_token === "string" &&
      token.token_type === "Bearer",
  );
}
