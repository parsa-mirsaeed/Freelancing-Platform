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
    return (
      <main className="dashboard-shell">
        <div className="dashboard-loading" role="status">
          Opening your workspace…
        </div>
      </main>
    );
  }
  if (!user) return null;

  const isEmployer = user.roles.includes("employer");
  const isFreelancer = user.roles.includes("freelancer");
  const primaryRole = isEmployer ? "Employer" : isFreelancer ? "Freelancer" : "Member";

  return (
    <main className="dashboard-shell">
      <section className="dashboard-welcome">
        <div>
          <p className="dashboard-context">{primaryRole} workspace</p>
          <h1>Welcome back.</h1>
          <p>{user.email}</p>
        </div>
        <Link className="dashboard-exit" href="/">
          Public marketplace
        </Link>
      </section>
      <section className="foundation-status" aria-labelledby="workspace-title">
        <div className="section-heading">
          <h2 id="workspace-title">Your marketplace workspace</h2>
          <p>
            The interface exposes only workflows your role can use; the backend still enforces every
            authorization and state transition.
          </p>
        </div>
        <div className="status-list">
          {isFreelancer ? (
            <article>
              <SparkIcon />
              <div>
                <strong>
                  <Link href="/dashboard/profile">Professional profile</Link>
                </strong>
                <span>Manage public expertise, rate guidance, availability, and portfolio.</span>
              </div>
            </article>
          ) : null}
          {isFreelancer ? (
            <article>
              <WalletIcon />
              <div>
                <strong>
                  <Link href="/dashboard/gigs">Services</Link>
                </strong>
                <span>Package active services with Basic, Standard, and Premium delivery terms.</span>
              </div>
            </article>
          ) : null}
          {isFreelancer ? (
            <article>
              <WalletIcon />
              <div>
                <strong>
                  <Link href="/dashboard/wallet">Wallet & payouts</Link>
                </strong>
                <span>Review ledger-derived balances; payouts require a recent MFA step-up.</span>
              </div>
            </article>
          ) : null}
          {isEmployer ? (
            <article>
              <SparkIcon />
              <div>
                <strong>
                  <Link href="/talent">Find talent</Link>
                </strong>
                <span>Search professionals by expertise and current availability.</span>
              </div>
            </article>
          ) : null}
          {isEmployer ? (
            <article>
              <WalletIcon />
              <div>
                <strong>
                  <Link href="/dashboard/projects">Projects</Link>
                </strong>
                <span>
                  Publish and refine open briefs; close only after backend completion rules pass.
                </span>
              </div>
            </article>
          ) : null}
          <article>
            <SparkIcon />
            <div>
              <strong>
                <Link href="/dashboard/messages">Messages & notifications</Link>
              </strong>
              <span>
                Open persisted contract chat, SAFE attachments, receipts, and notification
                preferences.
              </span>
            </div>
          </article>
          <article>
            <ShieldIcon />
            <div>
              <strong>
                <Link href="/dashboard/security">Security & MFA</Link>
              </strong>
              <span>Enroll an authenticator and step up this session for admin or payout actions.</span>
            </div>
          </article>
          <article>
            <ShieldIcon />
            <div>
              <strong>Secure session boundary</strong>
              <span>Browser JavaScript never receives access or refresh tokens.</span>
            </div>
          </article>
          <article>
            <WalletIcon />
            <div>
              <strong>Backend-aligned transport</strong>
              <span>Authenticated product requests flow through the same-origin BFF proxy.</span>
            </div>
          </article>
        </div>
      </section>
    </main>
  );
}
