import type { Metadata } from "next";

import { GigGrid, WorkHero } from "@/features/work/public-work";
import { readGigs } from "@/lib/server/work";

export const metadata: Metadata = {
  title: "Services",
  description: "Browse active freelancer services with package-level delivery terms.",
};

export default async function ServicesPage() {
  const gigs = await readGigs();
  return <main><WorkHero kind="services" /><GigGrid gigs={gigs} /></main>;
}
