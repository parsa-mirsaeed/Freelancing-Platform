import { productJson } from "@/lib/api/product-client";

export interface MfaStatus {
  enabled: boolean;
  verified_until: string | null;
  recovery_codes_remaining: number;
}

export interface MfaEnrollment {
  secret: string;
  otpauth_uri: string;
}

export interface MfaConfirmation {
  recovery_codes: string[];
  verified_until: string | null;
}

export interface MfaVerification {
  verified_until: string | null;
  recovery_code_used: boolean;
}

export function hasFreshMfa(status: MfaStatus, nowMs: number = Date.now()): boolean {
  if (!status.enabled || !status.verified_until) return false;
  const expiresAt = Date.parse(status.verified_until);
  return Number.isFinite(expiresAt) && expiresAt > nowMs;
}

export function needsMfaEnrollment(status: MfaStatus): boolean {
  return !status.enabled;
}

export function getMfaStatus(signal?: AbortSignal): Promise<MfaStatus> {
  return productJson<MfaStatus>("auth/mfa", { signal });
}

export function startMfaEnrollment(password: string): Promise<MfaEnrollment> {
  return productJson<MfaEnrollment>("auth/mfa/totp/enroll", {
    method: "POST",
    body: JSON.stringify({ password }),
  });
}

export function confirmMfaEnrollment(code: string): Promise<MfaConfirmation> {
  return productJson<MfaConfirmation>("auth/mfa/totp/confirm", {
    method: "POST",
    body: JSON.stringify({ code }),
  });
}

export function verifyMfa(code: string): Promise<MfaVerification> {
  return productJson<MfaVerification>("auth/mfa/verify", {
    method: "POST",
    body: JSON.stringify({ code }),
  });
}
