import Link from "next/link";
import { Suspense } from "react";

import { AuthForm } from "@/components/auth/auth-form";

export const metadata = { title: "Create account" };

export default function RegisterPage() {
  return (
    <main className="auth-page">
      <section className="auth-panel">
        <div className="auth-copy"><h1>Choose how you work.</h1><p>Your role controls authorization and the workspace we build around you. You can start as a freelancer or employer.</p></div>
        <Suspense fallback={<div className="auth-form-skeleton" aria-hidden="true" />}><AuthForm mode="register" /></Suspense>
        <p className="auth-switch">Already have an account? <Link href="/login">Sign in</Link></p>
      </section>
      <aside className="auth-aside auth-aside--register"><div><span className="auth-orbit" aria-hidden="true" /><h2>Clear roles.<br />Clear permissions.</h2><p>Role-aware routes mirror backend authorization rather than hiding actions only in the UI. The server remains the final authority.</p></div></aside>
    </main>
  );
}
