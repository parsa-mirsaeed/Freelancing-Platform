import type { Metadata } from "next";

import { ProjectGrid, WorkHero } from "@/features/work/public-work";
import { readProjects } from "@/lib/server/work";

export const metadata: Metadata = {
  title: "Projects",
  description: "Browse open client projects with skills and published budget ranges.",
};

export default async function ProjectsPage() {
  const projects = await readProjects();
  return <main><WorkHero kind="projects" /><ProjectGrid projects={projects} /></main>;
}
