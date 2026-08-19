"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect } from "react";

import { ShieldIcon, SparkIcon, WalletIcon } from "@/components/icons";
import { useSession } from "@/components/providers/session-provider";

export function DashboardClient() {
  const { user, status } = useSession();
  const router = useRouter();

  useEffect(() => {
    if (status === "anonymous") router.replace("/login?next=/dashboard");
  }, [router, status]);

  if (status === "loading") {
    return <main className="dashboard-shell"><div className="dashboard-loading" role="status">Opening your workspace…</div></main>;
  }
  if (!user) return null;

  const primaryRole = user.roles.includes("employer") ? "Employer" : user.roles.includes("freelancer") ? "Freelancer" : "Member";
  return (
    <main className="dashboard-shell">
      <section className="dashboard-welcome">
        <div><p className="dashboard-context">{primaryRole} workspace</p><h1>Welcome back.</h1><p>{user.email}</p></div>
        <Link className="dashboard-exit" href="/">Public marketplace</Link>
      </section>
      <section className="foundation-status" aria-labelledby="foundation-title">
        <div className="section-heading"><h2 id="foundation-title">Frontend foundation connected</h2><p>This first frontend slice establishes secure session handling and the product system. Domain workspaces arrive in the following PRs.</p></div>
        <div className="status-list">
          <article><ShieldIcon /><div><strong>HttpOnly session boundary</strong><span>Browser JavaScript never receives access or refresh tokens.</span></div></article>
          <article><WalletIcon /><div><strong>Backend-aligned transport</strong><span>Authenticated product requests flow through a same-origin BFF proxy.</span></div></article>
          <article><SparkIcon /><div><strong>Role-aware application shell</strong><span>Freelancer and employer workflows can now build on one consistent foundation.</span></div></article>
        </div>
      </section>
    </main>
  );
}
