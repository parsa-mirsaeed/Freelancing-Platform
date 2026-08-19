"use client";

import { MotionConfig } from "motion/react";
import type { ReactNode } from "react";

import { SessionProvider } from "@/components/providers/session-provider";

export function Providers({ children }: { children: ReactNode }) {
  return (
    <MotionConfig reducedMotion="user">
      <SessionProvider>{children}</SessionProvider>
    </MotionConfig>
  );
}
