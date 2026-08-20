import "server-only";

import { notFound } from "next/navigation";

import type { Gig, Project } from "@/lib/api/work";
import { backendFetch } from "@/lib/server/backend";

class WorkReadError extends Error {
  constructor(
    public readonly status: number,
    message: string,
  ) {
    super(message);
    this.name = "WorkReadError";
  }
}

async function readJson<T>(path: string): Promise<T> {
  const response = await backendFetch(path);
  if (!response.ok) {
    const payload = (await response.json().catch(() => null)) as
      | { error?: { message?: string }; message?: string }
      | null;
    throw new WorkReadError(
      response.status,
      payload?.error?.message ?? payload?.message ?? `Backend request failed with ${response.status}`,
    );
  }
  return (await response.json()) as T;
}

export async function readGigs(): Promise<Gig[]> {
  const payload = await readJson<{ items: Gig[] }>("/api/v1/gigs");
  return payload.items;
}

export async function readGig(gigId: string): Promise<Gig> {
  try {
    return await readJson<Gig>(`/api/v1/gigs/${encodeURIComponent(gigId)}`);
  } catch (error) {
    if (error instanceof WorkReadError && error.status === 404) notFound();
    throw error;
  }
}

export async function readProjects(): Promise<Project[]> {
  const payload = await readJson<{ items: Project[] }>("/api/v1/projects");
  return payload.items;
}

export async function readProject(projectId: string): Promise<Project> {
  try {
    return await readJson<Project>(`/api/v1/projects/${encodeURIComponent(projectId)}`);
  } catch (error) {
    if (error instanceof WorkReadError && error.status === 404) notFound();
    throw error;
  }
}
