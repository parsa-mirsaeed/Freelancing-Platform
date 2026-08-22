import type { Metadata } from "next";

import { GigDetail } from "@/features/work/public-work";
import { readGig } from "@/lib/server/work";

type Params = Promise<{ gigId: string }>;

export async function generateMetadata({ params }: { params: Params }): Promise<Metadata> {
  const { gigId } = await params;
  const gig = await readGig(gigId);
  return { title: gig.title, description: gig.description.slice(0, 155) };
}

export default async function ServiceDetailPage({ params }: { params: Params }) {
  const { gigId } = await params;
  return <GigDetail gig={await readGig(gigId)} />;
}
