"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useState } from "react";

import { MenuIcon } from "@/components/icons";
import { useSession } from "@/components/providers/session-provider";

const nav = [
  { href: "/talent", label: "Find talent" },
  { href: "/services", label: "Services" },
  { href: "/projects", label: "Projects" },
];

export function SiteHeader() {
  const { user, status, signOut } = useSession();
  const [open, setOpen] = useState(false);
  const pathname = usePathname();
  const router = useRouter();

  async function handleSignOut() {
    await signOut();
    router.push("/");
    router.refresh();
  }

  const authenticated = status === "authenticated" && Boolean(user);

  return (
    <header className="site-header" data-path={pathname}>
      <div className="header-inner">
        <Link className="brand" href="/" aria-label="Freelancing Platform home">
          <span className="brand-mark" aria-hidden="true"><span /></span>
          <span>Freelancing Platform</span>
        </Link>
        <nav className="desktop-nav" aria-label="Primary navigation">
          {nav.map((item) => <Link key={item.href} href={item.href}>{item.label}</Link>)}
        </nav>
        <div className="header-actions">
          {authenticated ? (
            <>
              <Link className="header-quiet" href="/dashboard">Dashboard</Link>
              <button className="header-primary" type="button" onClick={handleSignOut}>Sign out</button>
            </>
          ) : (
            <>
              <Link className="header-quiet" href="/login">Sign in</Link>
              <Link className="header-primary" href="/register">Join the platform</Link>
            </>
          )}
        </div>
        <button className="mobile-menu-button" type="button" aria-label="Toggle navigation" aria-expanded={open} onClick={() => setOpen((value) => !value)}>
          <MenuIcon width="22" height="22" />
        </button>
      </div>
      {open ? (
        <nav className="mobile-nav" aria-label="Mobile navigation">
          {nav.map((item) => <Link key={item.href} href={item.href} onClick={() => setOpen(false)}>{item.label}</Link>)}
          {authenticated ? (
            <>
              <Link href="/dashboard" onClick={() => setOpen(false)}>Dashboard</Link>
              <button type="button" onClick={() => { setOpen(false); void handleSignOut(); }}>Sign out</button>
            </>
          ) : (
            <>
              <Link href="/login" onClick={() => setOpen(false)}>Sign in</Link>
              <Link href="/register" onClick={() => setOpen(false)}>Join the platform</Link>
            </>
          )}
        </nav>
      ) : null}
    </header>
  );
}
