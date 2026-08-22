import type { Metadata } from "next";

import { GigWorkspace } from "@/features/work/gig-workspace";

export const metadata: Metadata = {
  title: "Services workspace",
  description: "Create and manage active freelancer service packages.",
};

export default function DashboardGigsPage() {
  return <GigWorkspace />;
}
