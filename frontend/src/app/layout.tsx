import type { Metadata, Viewport } from "next";
import type { ReactNode } from "react";

import "./globals.css";
import "./route-theme.css";
import "./marketplace.css";
import { Providers } from "@/app/providers";
import { SiteFooter } from "@/components/shell/site-footer";
import { SiteHeader } from "@/components/shell/site-header";

export const metadata: Metadata = {
  title: { default: "Freelancing Platform", template: "%s · Freelancing Platform" },
  description: "A secure skill-sharing and freelancing marketplace for hiring, delivering, and getting paid.",
};

export const viewport: Viewport = {
  width: "device-width",
  initialScale: 1,
  colorScheme: "light dark",
  themeColor: "#07120f",
};

export default function RootLayout({ children }: Readonly<{ children: ReactNode }>) {
  return (
    <html lang="en">
      <body>
        <a className="skip-link" href="#main-content">Skip to content</a>
        <Providers>
          <SiteHeader />
          <div id="main-content">{children}</div>
          <SiteFooter />
        </Providers>
      </body>
    </html>
  );
}
