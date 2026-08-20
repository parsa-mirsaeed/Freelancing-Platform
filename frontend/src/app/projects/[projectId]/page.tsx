import type { Metadata } from "next";

import { ProjectDetail } from "@/features/work/public-work";
import { readProject } from "@/lib/server/work";

type Params = Promise<{ projectId: string }>;

export async function generateMetadata({ params }: { params: Params }): Promise<Metadata> {
  const { projectId } = await params;
  const project = await readProject(projectId);
  return { title: project.title, description: project.description.slice(0, 155) };
}

export default async function ProjectDetailPage({ params }: { params: Params }) {
  const { projectId } = await params;
  return <ProjectDetail project={await readProject(projectId)} />;
}
