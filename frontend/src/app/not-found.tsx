import { ActionLink } from "@/components/ui/action-link";

export default function NotFound() {
  return <main className="state-page"><div><span>404</span><h1>This workspace does not exist.</h1><p>The link may be stale, private, or no longer available.</p><ActionLink href="/">Back to marketplace</ActionLink></div></main>;
}
