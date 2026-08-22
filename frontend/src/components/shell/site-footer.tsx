import Link from "next/link";

export function SiteFooter() {
  return (
    <footer className="site-footer">
      <div className="footer-inner">
        <div>
          <div className="brand brand--footer"><span className="brand-mark" aria-hidden="true"><span /></span><span>Freelancing Platform</span></div>
          <p>A secure workspace for discovering expertise, agreeing on work, collaborating, and settling outcomes.</p>
        </div>
        <div className="footer-links" aria-label="Footer navigation">
          <Link href="/#workflow">Workflow</Link>
          <Link href="/#capabilities">Platform</Link>
          <Link href="/login">Sign in</Link>
        </div>
      </div>
    </footer>
  );
}
