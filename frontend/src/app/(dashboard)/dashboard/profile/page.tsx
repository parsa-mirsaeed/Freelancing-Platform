import type { Metadata } from "next";

import { ProfileWorkspace } from "@/features/profile/profile-workspace";

export const metadata: Metadata = {
  title: "Professional profile",
  description: "Manage freelancer profile, availability, and portfolio.",
};

export default function DashboardProfilePage() {
  return <ProfileWorkspace />;
}
