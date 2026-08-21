import type { Metadata } from "next";

import { ProfileEditor } from "@/components/profile/profile-editor";

export const metadata: Metadata = {
  title: "Professional profile",
};

export default function ProfileStudioPage() {
  return <ProfileEditor />;
}
