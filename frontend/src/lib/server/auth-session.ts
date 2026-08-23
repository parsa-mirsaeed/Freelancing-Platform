import "server-only";

import { cookies } from "next/headers";
import { NextResponse } from "next/server";

export interface SessionTokens {
  access_token: string;
  refresh_token: string;
  token_type: "Bearer";
}

export const ACCESS_COOKIE = "fp_access";
export const REFRESH_COOKIE = "fp_refresh";
export const DEVICE_COOKIE = "fp_device";

const secure = process.env.NODE_ENV === "production";

export async function readSessionTokens(): Promise<{ access?: string; refresh?: string }> {
  const store = await cookies();
  return {
    access: store.get(ACCESS_COOKIE)?.value,
    refresh: store.get(REFRESH_COOKIE)?.value,
  };
}

export async function readDeviceId(): Promise<string | undefined> {
  const store = await cookies();
  return store.get(DEVICE_COOKIE)?.value;
}

export function applySessionCookies(response: NextResponse, tokens: SessionTokens): void {
  response.cookies.set(ACCESS_COOKIE, tokens.access_token, {
    httpOnly: true,
    sameSite: "lax",
    secure,
    path: "/",
    maxAge: 15 * 60,
  });
  response.cookies.set(REFRESH_COOKIE, tokens.refresh_token, {
    httpOnly: true,
    sameSite: "lax",
    secure,
    path: "/",
    maxAge: 30 * 24 * 60 * 60,
  });
}

export function applyDeviceCookie(response: NextResponse, deviceId: string): void {
  response.cookies.set(DEVICE_COOKIE, deviceId, {
    httpOnly: true,
    sameSite: "lax",
    secure,
    path: "/",
    maxAge: 365 * 24 * 60 * 60,
  });
}

export function clearSessionCookies(response: NextResponse): void {
  const base = { httpOnly: true, sameSite: "lax" as const, secure, path: "/", maxAge: 0 };
  response.cookies.set(ACCESS_COOKIE, "", base);
  response.cookies.set(REFRESH_COOKIE, "", base);
}
