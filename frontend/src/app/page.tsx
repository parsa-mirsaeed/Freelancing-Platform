import { ArrowRightIcon, MessageIcon, ShieldIcon, SparkIcon, WalletIcon } from "@/components/icons";
import { Reveal } from "@/components/motion/reveal";
import { ActionLink } from "@/components/ui/action-link";

const workflow = [
  ["01", "Discover", "Search expertise or publish a project with clear commercial terms."],
  ["02", "Agree", "Compare proposals, negotiate versions, and sign an immutable contract snapshot."],
  ["03", "Fund", "Move milestone value into ledger-backed escrow before work begins."],
  ["04", "Deliver", "Collaborate in one conversation, share safe files, and track milestone state."],
  ["05", "Settle", "Approve and release, or open a dispute with an auditable evidence trail."],
] as const;

const capabilities = [
  { icon: ShieldIcon, title: "Contract-first trust", text: "Versioned proposals, immutable contract snapshots, signatures, milestone state machines, and explicit authorization boundaries." },
  { icon: WalletIcon, title: "Ledger-backed money", text: "Escrow, releases, refunds, wallet balances, and payouts are represented by balanced double-entry accounting—not a mutable balance field." },
  { icon: MessageIcon, title: "Realtime workroom", text: "Durable messaging, delivery and read state, safe file handling, notifications, presence, and peer-to-peer call signaling." },
  { icon: SparkIcon, title: "Explainable assistance", text: "Deterministic matching, skill suggestions, price intervals, and human-reviewed risk signals without opaque automatic enforcement." },
] as const;

export default function Home() {
  return (
    <main>
      <section className="hero">
        <div className="hero-grid" aria-hidden="true" />
        <div className="hero-glow hero-glow--one" aria-hidden="true" />
        <div className="hero-glow hero-glow--two" aria-hidden="true" />
        <div className="hero-inner">
          <Reveal className="hero-copy">
            <h1>Hire expertise.<br /><span>Build without friction.</span></h1>
            <p>A modern marketplace for independent work—from discovery and negotiation to protected payment, collaboration, and resolution.</p>
            <div className="hero-actions">
              <ActionLink href="/register">Start hiring <ArrowRightIcon width="18" height="18" /></ActionLink>
              <ActionLink href="/register" variant="secondary">Offer your skills</ActionLink>
            </div>
            <div className="hero-assurance"><ShieldIcon width="18" height="18" /><span>Commercial state is explicit, auditable, and permission-aware.</span></div>
          </Reveal>
          <Reveal className="hero-system" delay={0.08}>
            <div className="system-frame">
              <div className="system-topline"><span>Project workspace</span><span className="live-state"><i /> Contract active</span></div>
              <div className="system-title-row"><div><small>Brand system implementation</small><strong>Milestone 02 · Interaction layer</strong></div><span className="system-amount">$2,400</span></div>
              <div className="milestone-track"><span className="track-done" /><span className="track-done" /><span className="track-active" /><span /><span /></div>
              <div className="system-columns">
                <div className="system-panel"><span className="panel-label">Progress</span><div className="progress-ring"><strong>64%</strong><span>complete</span></div><div className="panel-note"><i /> Work submitted securely</div></div>
                <div className="system-panel system-panel--activity"><span className="panel-label">Recent activity</span><ul><li><i className="dot dot--green" /><span><strong>Milestone funded</strong><small>Escrow confirmed</small></span></li><li><i className="dot" /><span><strong>New message</strong><small>Feedback on interaction states</small></span></li><li><i className="dot dot--blue" /><span><strong>File verified</strong><small>prototype-v7.fig</small></span></li></ul></div>
              </div>
              <div className="floating-signal signal-one"><span>AI match</span><strong>Relevant skills aligned</strong></div>
              <div className="floating-signal signal-two"><span>Protected</span><strong>Funds in escrow</strong></div>
            </div>
          </Reveal>
        </div>
      </section>

      <section className="role-band" aria-label="Marketplace roles">
        <Reveal className="role-band-inner">
          <div><span>For employers</span><h2>Turn a scoped idea into accountable delivery.</h2><p>Publish projects, compare proposals, contract milestones, fund escrow, review progress, and release when work is approved.</p></div>
          <div className="role-divider" aria-hidden="true" />
          <div><span>For freelancers</span><h2>Package expertise and protect the way you get paid.</h2><p>Build a professional profile, publish gigs, propose on projects, collaborate in real time, and withdraw ledger-derived earnings.</p></div>
        </Reveal>
      </section>

      <section className="workflow-section" id="workflow">
        <div className="content-shell">
          <Reveal className="section-heading section-heading--wide"><h2>One continuous workflow from intent to outcome.</h2><p>The interface follows the same state transitions enforced by the backend, so users see what can happen next—and why.</p></Reveal>
          <div className="workflow-list">
            {workflow.map(([number, title, text], index) => <Reveal key={title} className="workflow-row" delay={index * 0.035}><span>{number}</span><h3>{title}</h3><p>{text}</p><ArrowRightIcon width="18" height="18" /></Reveal>)}
          </div>
        </div>
      </section>

      <section className="capabilities-section" id="capabilities">
        <div className="content-shell">
          <Reveal className="section-heading"><h2>Designed around the hard parts of independent work.</h2><p>Trust, money, communication, and decision support share one product language instead of feeling like disconnected tools.</p></Reveal>
          <div className="capability-grid">
            {capabilities.map(({ icon: Icon, title, text }, index) => <Reveal key={title} className="capability" delay={index * 0.045}><div className="capability-icon"><Icon width="23" height="23" /></div><h3>{title}</h3><p>{text}</p></Reveal>)}
          </div>
        </div>
      </section>

      <section className="closing-section">
        <Reveal className="closing-card">
          <div><h2>Work should feel ambitious—not fragile.</h2><p>Join as an employer or freelancer. The product adapts the workspace to the role you actually perform.</p></div>
          <ActionLink href="/register">Create your workspace <ArrowRightIcon width="18" height="18" /></ActionLink>
        </Reveal>
      </section>
    </main>
  );
}
