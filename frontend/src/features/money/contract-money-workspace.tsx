"use client";

import { useEffect, useMemo, useState } from "react";

import { useSession } from "@/components/providers/session-provider";
import { memberRoleForContract, type Contract } from "@/lib/api/contracts";
import { productJson } from "@/lib/api/product-client";

import contractStyles from "./contract-money.module.css";
import { MilestoneMoney } from "./milestone-money";
import styles from "./money.module.css";

function contractPath(contractId?: string, projectId?: string): string | null {
  if (contractId) return `contracts/${contractId}`;
  if (projectId) return `projects/${projectId}/contract`;
  return null;
}

export function ContractMoneyWorkspace({
  contractId,
  projectId,
}: {
  contractId?: string;
  projectId?: string;
}) {
  const { user, status } = useSession();
  const [contract, setContract] = useState<Contract | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    if (status !== "authenticated" || !user) return;
    const path = contractPath(contractId, projectId);
    if (!path) return;
    const controller = new AbortController();
    void productJson<Contract>(path, { signal: controller.signal })
      .then((next) => {
        setContract(next);
        setError("");
      })
      .catch((reason: unknown) => {
        if (controller.signal.aborted) return;
        setError(reason instanceof Error ? reason.message : "Unable to load contract money state.");
      });
    return () => controller.abort();
  }, [contractId, projectId, status, user]);

  const role = useMemo(
    () => (contract && user ? memberRoleForContract(contract, user.id) : null),
    [contract, user],
  );

  async function refreshContract() {
    const path = contractPath(contractId, projectId);
    if (!path) return;
    const next = await productJson<Contract>(path);
    setContract(next);
  }

  if (status !== "authenticated" || !user) return null;

  if (!contract || !role) {
    return (
      <section className={contractStyles.panel} aria-labelledby="money-heading">
        <div className={styles.walletHeading}>
          <div>
            <span>Financial source of truth</span>
            <h2 id="money-heading">Escrow & release</h2>
          </div>
        </div>
        <p className={error ? styles.inlineError : styles.loading} role={error ? "alert" : "status"}>
          {error || "Loading backend financial state…"}
        </p>
      </section>
    );
  }

  return (
    <section className={contractStyles.panel} aria-labelledby="money-heading">
      <div className={styles.walletHeading}>
        <div>
          <span>Financial source of truth</span>
          <h2 id="money-heading">Escrow & release</h2>
        </div>
        <p>
          Financial totals are read from the backend ledger projection. Employer controls mirror
          backend eligibility, but backend authorization, locking, idempotency, and invariants remain
          authoritative.
        </p>
      </div>

      {error ? <p className={styles.inlineError} role="alert">{error}</p> : null}

      <div className={contractStyles.list}>
        {contract.version.milestones.map((milestone) => (
          <article className={contractStyles.card} key={milestone.id}>
            <header>
              <div>
                <span>Milestone {String(milestone.sequence).padStart(2, "0")}</span>
                <h3>{milestone.title}</h3>
              </div>
              <strong data-status={milestone.status}>
                {milestone.status.replaceAll("_", " ")}
              </strong>
            </header>
            <MilestoneMoney
              milestone={milestone}
              role={role}
              contractStatus={contract.status}
              onAuthoritativeMutation={refreshContract}
            />
          </article>
        ))}
      </div>
    </section>
  );
}
