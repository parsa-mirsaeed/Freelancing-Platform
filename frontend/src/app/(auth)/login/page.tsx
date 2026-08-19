import Link from "next/link";
import { Suspense } from "react";

import { AuthForm } from "@/components/auth/auth-form";

export const metadata = { title: "Sign in" };

export default function LoginPage() {
  return (
    <main className="auth-page">
      <section className="auth-panel">
        <div className="auth-copy"><h1>Welcome back.</h1><p>Sign in to continue to your contracts, projects, proposals, and workrooms.</p></div>
        <Suspense fallback={<div className="auth-form-skeleton" aria-hidden="true" />}><AuthForm mode="login" /></Suspense>
        <p className="auth-switch">New here? <Link href="/register">Create an account</Link></p>
      </section>
      <aside className="auth-aside"><div><span className="auth-orbit" aria-hidden="true" /><h2>One identity.<br />Every work state.</h2><p>Authentication is exchanged server-side and stored in HttpOnly cookies. Access and refresh tokens are never exposed to browser JavaScript.</p></div></aside>
    </main>
  );
}
