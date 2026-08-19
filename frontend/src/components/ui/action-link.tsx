import Link from "next/link";
import type { ReactNode } from "react";

interface ActionLinkProps {
  href: string;
  children: ReactNode;
  variant?: "primary" | "secondary" | "quiet";
  className?: string;
}

export function ActionLink({ href, children, variant = "primary", className = "" }: ActionLinkProps) {
  return <Link className={`action-link action-link--${variant} ${className}`.trim()} href={href}>{children}</Link>;
}
