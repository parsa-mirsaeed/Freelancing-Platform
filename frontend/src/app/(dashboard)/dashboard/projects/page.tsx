import type { Metadata } from "next";

import { ProjectWorkspace } from "@/features/work/project-workspace";

export const metadata: Metadata = {
  title: "Projects workspace",
  description: "Publish and manage open employer project briefs.",
};

export default function DashboardProjectsPage() {
  return <ProjectWorkspace />;
}
