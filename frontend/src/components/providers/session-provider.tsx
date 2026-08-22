"use client";

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";

import type { SessionUser } from "@/lib/api/types";

interface SessionValue {
  user: SessionUser | null;
  status: "loading" | "authenticated" | "anonymous";
  refresh: () => Promise<void>;
  signOut: () => Promise<void>;
}

const SessionContext = createContext<SessionValue | null>(null);

async function requestSession(signal?: AbortSignal): Promise<SessionUser | null> {
  const response = await fetch("/api/session/me", { cache: "no-store", signal });
  if (!response.ok) return null;
  return (await response.json()) as SessionUser;
}

export function SessionProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<SessionUser | null>(null);
  const [status, setStatus] = useState<SessionValue["status"]>("loading");

  const refresh = useCallback(async () => {
    try {
      const nextUser = await requestSession();
      setUser(nextUser);
      setStatus(nextUser ? "authenticated" : "anonymous");
    } catch {
      setUser(null);
      setStatus("anonymous");
    }
  }, []);

  const signOut = useCallback(async () => {
    await fetch("/api/session/logout", { method: "POST" }).catch(() => undefined);
    setUser(null);
    setStatus("anonymous");
  }, []);

  useEffect(() => {
    const controller = new AbortController();
    void requestSession(controller.signal)
      .then((nextUser) => {
        setUser(nextUser);
        setStatus(nextUser ? "authenticated" : "anonymous");
      })
      .catch((error: unknown) => {
        if (error instanceof DOMException && error.name === "AbortError") return;
        setUser(null);
        setStatus("anonymous");
      });
    return () => controller.abort();
  }, []);

  const value = useMemo(
    () => ({ user, status, refresh, signOut }),
    [user, status, refresh, signOut],
  );
  return <SessionContext.Provider value={value}>{children}</SessionContext.Provider>;
}

export function useSession(): SessionValue {
  const value = useContext(SessionContext);
  if (!value) throw new Error("useSession must be used inside SessionProvider");
  return value;
}
