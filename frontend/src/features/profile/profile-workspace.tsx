"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";

import { useSession } from "@/components/providers/session-provider";
import { AvailabilityEditor } from "@/features/profile/availability-editor";
import { PortfolioEditor } from "@/features/profile/portfolio-editor";
import { ProductApiError, productJson } from "@/features/profile/profile-api";
import { ProfileForm } from "@/features/profile/profile-form";
import type { FreelancerProfile, PortfolioItem } from "@/lib/api/marketplace";

import styles from "./profile-workspace.module.css";

export function ProfileWorkspace() {
  const { user, status } = useSession();
  const router = useRouter();
  const [profile, setProfile] = useState<FreelancerProfile | null>(null);
  const [portfolio, setPortfolio] = useState<PortfolioItem[]>([]);
  const [loadState, setLoadState] = useState<"waiting" | "ready" | "error">("waiting");
  const [loadError, setLoadError] = useState("");
  const isFreelancer = Boolean(user?.roles.includes("freelancer"));

  useEffect(() => {
    if (status === "anonymous") {
      router.replace("/login?next=/dashboard/profile");
      return;
    }
    if (status !== "authenticated" || !user || !user.roles.includes("freelancer")) return;

    let cancelled = false;
    void productJson<FreelancerProfile>("freelancers/me/profile")
      .catch((error: unknown) => {
        if (error instanceof ProductApiError && error.status === 404) return null;
        throw error;
      })
      .then(async (nextProfile) => {
        if (cancelled) return;
        setProfile(nextProfile);
        if (!nextProfile) {
          setPortfolio([]);
          setLoadState("ready");
          return;
        }
        const payload = await productJson<{ items: PortfolioItem[] }>(`freelancers/${user.id}/portfolio`);
        if (cancelled) return;
        setPortfolio(payload.items);
        setLoadState("ready");
      })
      .catch((error: unknown) => {
        if (cancelled) return;
        setLoadError(error instanceof Error ? error.message : "Profile workspace could not be loaded.");
        setLoadState("error");
      });

    return () => { cancelled = true; };
  }, [router, status, user]);

  if (status === "loading" || (isFreelancer && loadState === "waiting")) {
    return <main className={styles.page}><div className={styles.loading} role="status">Loading professional workspace…</div></main>;
  }
  if (!user) return null;
  if (!isFreelancer) {
    return <main className={styles.page}><div className={styles.roleState}><span>Freelancer workspace</span><h1>This area is for freelancer accounts.</h1><p>Your account roles do not include freelancer access. Backend authorization remains authoritative.</p><Link href="/dashboard">Return to dashboard</Link></div></main>;
  }
  if (loadState === "error") {
    return <main className={styles.page}><div className={styles.roleState}><span>Could not load profile</span><h1>Professional workspace is unavailable.</h1><p>{loadError}</p><button type="button" onClick={() => window.location.reload()}>Retry</button></div></main>;
  }

  return (
    <main className={styles.page}>
      <header className={styles.hero}>
        <div>
          <Link href="/dashboard">← Dashboard</Link>
          <span>Freelancer workspace</span>
          <h1>Shape the profile employers evaluate.</h1>
          <p>Keep identity, pricing guidance, availability, and proof of work current. Commercial commitments still happen through versioned proposals and contracts.</p>
        </div>
        {profile ? <Link className={styles.publicLink} href={`/talent/${profile.user_id}`}>View public profile ↗</Link> : null}
      </header>
      {!profile ? <div className={styles.onboarding}><strong>Your public profile is not published yet.</strong><p>Complete the profile section first. Availability and portfolio controls appear immediately after the backend creates the profile.</p></div> : null}
      <div className={styles.workspace}>
        <ProfileForm profile={profile} onSaved={setProfile} />
        {profile ? <AvailabilityEditor key={`availability-${profile.projection_version}`} profile={profile} /> : null}
        {profile ? <PortfolioEditor initialItems={portfolio} /> : null}
      </div>
    </main>
  );
}
