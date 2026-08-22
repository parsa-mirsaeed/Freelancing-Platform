import Link from "next/link";

import { DashboardClient } from "@/components/dashboard/dashboard-client";

export const metadata = { title: "Dashboard" };

export default function DashboardPage() {
  return (
    <>
      <DashboardClient />
      <p style={{ width: "min(1180px, calc(100% - 40px))", margin: "-56px auto 88px" }}>
        <Link href="/dashboard/disputes">
          Open dispute cases and arbitration queue →
        </Link>
      </p>
    </>
  );
}
