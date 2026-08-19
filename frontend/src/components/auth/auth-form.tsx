"use client";

import { useRouter, useSearchParams } from "next/navigation";
import { useState, type FormEvent } from "react";

import { ArrowRightIcon } from "@/components/icons";
import { useSession } from "@/components/providers/session-provider";
import { apiErrorMessage } from "@/lib/api/types";

interface AuthFormProps {
  mode: "login" | "register";
}

export function AuthForm({ mode }: AuthFormProps) {
  const router = useRouter();
  const search = useSearchParams();
  const { refresh } = useSession();
  const [pending, setPending] = useState(false);
  const [error, setError] = useState("");

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError("");
    setPending(true);
    const form = new FormData(event.currentTarget);
    const payload: Record<string, string> = {
      email: String(form.get("email") ?? ""),
      password: String(form.get("password") ?? ""),
    };
    if (mode === "register") payload.role = String(form.get("role") ?? "freelancer");

    try {
      const response = await fetch(`/api/session/${mode}`, {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify(payload),
      });
      const body: unknown = await response.json().catch(() => ({}));
      if (!response.ok) {
        setError(apiErrorMessage(body, mode === "login" ? "Unable to sign in." : "Unable to create the account."));
        return;
      }
      await refresh();
      const target = search.get("next");
      router.replace(target?.startsWith("/") && !target.startsWith("//") ? target : "/dashboard");
      router.refresh();
    } catch {
      setError("The platform could not be reached. Check that the backend is running and try again.");
    } finally {
      setPending(false);
    }
  }

  return (
    <form className="auth-form" onSubmit={submit}>
      <div className="field-group">
        <label htmlFor="email">Email address</label>
        <input id="email" name="email" type="email" inputMode="email" autoComplete="email" required placeholder="you@example.com" />
      </div>
      <div className="field-group">
        <div className="field-label-row"><label htmlFor="password">Password</label>{mode === "register" ? <span>12+ characters</span> : null}</div>
        <input id="password" name="password" type="password" autoComplete={mode === "login" ? "current-password" : "new-password"} minLength={mode === "register" ? 12 : undefined} required />
      </div>
      {mode === "register" ? (
        <fieldset className="role-fieldset">
          <legend>I want to</legend>
          <label><input type="radio" name="role" value="freelancer" defaultChecked /><span><strong>Offer my skills</strong><small>Create services and send proposals.</small></span></label>
          <label><input type="radio" name="role" value="employer" /><span><strong>Hire expertise</strong><small>Post projects and compare proposals.</small></span></label>
        </fieldset>
      ) : null}
      {error ? <div className="form-error" role="alert">{error}</div> : null}
      <button className="auth-submit" type="submit" disabled={pending}>
        <span>{pending ? "Working…" : mode === "login" ? "Sign in securely" : "Create account"}</span>
        <ArrowRightIcon width="18" height="18" />
      </button>
    </form>
  );
}
