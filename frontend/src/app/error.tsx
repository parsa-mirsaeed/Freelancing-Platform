"use client";

export default function GlobalError({ reset }: { error: Error & { digest?: string }; reset: () => void }) {
  return <main className="state-page"><div><span>Unexpected state</span><h1>We could not render this view.</h1><p>Your data has not been changed. Retry the view, or return to the marketplace.</p><button className="auth-submit state-reset" type="button" onClick={reset}>Try again</button></div></main>;
}
