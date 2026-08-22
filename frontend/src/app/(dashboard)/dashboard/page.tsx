import Link from "next/link";

import { DashboardClient } from "@/components/dashboard/dashboard-client";

export const metadata = { title: "Dashboard" };

export default function DashboardPage() {
  return (
    <>
      <DashboardClient />
      <div
        style={{
          width: "min(1180px, calc(100% - 40px))",
          margin: "-56px auto 88px",
          display: "flex",
          flexWrap: "wrap",
          gap: "16px",
        }}
      >
        <Link href="/dashboard/disputes">Open dispute cases and arbitration queue →</Link>
        <Link href="/dashboard/calls">Open voice, video, and screen-sharing calls →</Link>
        <Link href="/dashboard/ai">Open explainable AI assistance →</Link>
      </div>
    </>
  );
}
