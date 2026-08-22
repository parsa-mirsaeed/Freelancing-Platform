import Link from "next/link";

import type { Gig, Project } from "@/lib/api/work";
import { minimumGigPackage, sortGigPackages } from "@/lib/api/work";
import { formatMinorMoney } from "@/lib/intl";

import styles from "./work.module.css";

function budget(project: Project): string {
  if (
    project.budget_min_minor === null ||
    project.budget_max_minor === null ||
    project.currency === null
  ) {
    return "Budget discussed in proposal";
  }
  return `${formatMinorMoney(project.budget_min_minor, project.currency)} – ${formatMinorMoney(project.budget_max_minor, project.currency)}`;
}

export function WorkHero({ kind }: { kind: "services" | "projects" }) {
  const service = kind === "services";
  return (
    <section className={styles.hero}>
      <div className={styles.heroInner}>
        <p>{service ? "Packaged expertise" : "Open client work"}</p>
        <h1>{service ? "Buy a defined service with clear delivery terms." : "Find serious project briefs worth solving."}</h1>
        <span>
          {service
            ? "Compare Basic, Standard, and Premium packages exactly as freelancers publish them."
            : "Browse open projects with explicit skills and budget ranges; proposals remain the commercial source of truth."}
        </span>
      </div>
    </section>
  );
}

export function GigGrid({ gigs }: { gigs: Gig[] }) {
  if (gigs.length === 0) return <p className={styles.empty}>No active services are published yet.</p>;
  return (
    <div className={styles.grid}>
      {gigs.map((gig) => {
        const starting = minimumGigPackage(gig);
        return (
          <article className={styles.card} key={gig.id}>
            <div className={styles.cardVisual} aria-hidden="true"><span>{gig.title.slice(0, 1).toUpperCase()}</span></div>
            <div className={styles.cardBody}>
              <div className={styles.cardMeta}><span>{gig.packages.length} package{gig.packages.length === 1 ? "" : "s"}</span><span>{gig.requirements.length} requirement{gig.requirements.length === 1 ? "" : "s"}</span></div>
              <h2><Link href={`/services/${gig.id}`}>{gig.title}</Link></h2>
              <p>{gig.description}</p>
              <div className={styles.cardFooter}>
                <span>Starting at</span>
                <strong>{starting ? formatMinorMoney(starting.amount_minor, starting.currency) : "—"}</strong>
              </div>
            </div>
          </article>
        );
      })}
    </div>
  );
}

export function ProjectGrid({ projects }: { projects: Project[] }) {
  if (projects.length === 0) return <p className={styles.empty}>No open projects are published yet.</p>;
  return (
    <div className={styles.projectList}>
      {projects.map((project) => (
        <article className={styles.projectCard} key={project.id}>
          <div>
            <div className={styles.cardMeta}><span>{project.status}</span><span>{project.skills.length} skill{project.skills.length === 1 ? "" : "s"}</span></div>
            <h2><Link href={`/projects/${project.id}`}>{project.title}</Link></h2>
            <p>{project.description}</p>
            <div className={styles.skills}>{project.skills.map((skill) => <span key={skill}>{skill}</span>)}</div>
          </div>
          <aside><span>Budget</span><strong>{budget(project)}</strong><Link href={`/projects/${project.id}`}>Review brief →</Link></aside>
        </article>
      ))}
    </div>
  );
}

export function GigDetail({ gig }: { gig: Gig }) {
  const packages = sortGigPackages(gig.packages);
  return (
    <main className={styles.detailPage}>
      <section className={styles.detailHero}>
        <div><Link href="/services">← All services</Link><h1>{gig.title}</h1><p>{gig.description}</p></div>
      </section>
      <section className={styles.detailBody}>
        <div className={styles.packageGrid}>
          {packages.map((item) => (
            <article key={item.id}>
              <span>{item.tier}</span>
              <strong>{formatMinorMoney(item.amount_minor, item.currency)}</strong>
              <p>{item.description || "Defined scope with the published delivery terms below."}</p>
              <dl>
                <div><dt>Delivery</dt><dd>{item.delivery_days} day{item.delivery_days === 1 ? "" : "s"}</dd></div>
                <div><dt>Revisions</dt><dd>{item.revisions}</dd></div>
              </dl>
            </article>
          ))}
        </div>
        <div className={styles.requirements}>
          <div><span>Before work starts</span><h2>Client requirements</h2></div>
          {gig.requirements.length ? <ol>{gig.requirements.map((item) => <li key={item.id}><span>{item.required ? "Required" : "Optional"}</span><strong>{item.prompt}</strong></li>)}</ol> : <p>No intake requirements are published for this service.</p>}
        </div>
      </section>
    </main>
  );
}

export function ProjectDetail({ project }: { project: Project }) {
  return (
    <main className={styles.detailPage}>
      <section className={styles.detailHero}>
        <div><Link href="/projects">← Open projects</Link><div className={styles.cardMeta}><span>{project.status}</span><span>Employer brief</span></div><h1>{project.title}</h1><p>{project.description}</p></div>
      </section>
      <section className={styles.projectDetailBody}>
        <div><span>Required expertise</span><div className={styles.skills}>{project.skills.map((skill) => <span key={skill}>{skill}</span>)}</div></div>
        <aside>
          <span>Published budget</span>
          <strong>{budget(project)}</strong>
          <p>Final milestones, delivery terms, and price are captured in the accepted proposal and contract.</p>
          <Link href={`/projects/${project.id}/proposal`}>Submit a proposal</Link>
        </aside>
      </section>
    </main>
  );
}
