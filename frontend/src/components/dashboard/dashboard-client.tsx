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

  const freelancer = user.roles.includes("freelancer");
  const employer = user.roles.includes("employer");
  const primaryRole = employer ? "Employer" : freelancer ? "Freelancer" : "Member";

  return (
    <main className="dashboard-shell">
      <section className="dashboard-welcome">
        <div><p className="dashboard-context">{primaryRole} workspace</p><h1>Welcome back.</h1><p>{user.email}</p></div>
        <Link className="dashboard-exit" href="/talent">Public marketplace</Link>
      </section>
      <section className="foundation-status" aria-labelledby="workspace-title">
        <div className="section-heading"><h2 id="workspace-title">Your next workspace</h2><p>The frontend now connects the marketplace discovery and professional profile domains while backend authorization remains authoritative.</p></div>
        <div className="status-list">
          {freelancer ? (
            <article><SparkIcon /><div><strong>Professional profile</strong><span>Publish expertise, languages, exact rate, availability, and portfolio.</span><Link href="/dashboard/profile">Open profile studio →</Link></div></article>
          ) : null}
          {employer ? (
            <article><SparkIcon /><div><strong>Talent discovery</strong><span>Search the Elasticsearch projection by expertise, skills, and availability.</span><Link href="/talent">Find talent →</Link></div></article>
          ) : null}
          <article><ShieldIcon /><div><strong>Server-side session boundary</strong><span>Browser JavaScript never receives access or refresh tokens.</span></div></article>
          <article><WalletIcon /><div><strong>Backend-authoritative marketplace</strong><span>Profile writes and search results use the existing Flask domain APIs without client-side policy duplication.</span></div></article>
        </div>
      </section>
    </main>
  );
}
