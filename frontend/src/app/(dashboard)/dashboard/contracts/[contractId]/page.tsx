import type { Metadata } from "next";
import Link from "next/link";

import { ContractWorkspace } from "@/features/contracts/contract-workspace";
import { ContractMoneyWorkspace } from "@/features/money/contract-money-workspace";

export const metadata: Metadata = {
  title: "Contract workspace",
  description: "Review immutable contract execution and backend-authoritative milestone finances.",
};

type Params = Promise<{ contractId: string }>;

export default async function ContractPage({ params }: { params: Params }) {
  const { contractId } = await params;
  return (
    <>
      <ContractWorkspace contractId={contractId} />
      <ContractMoneyWorkspace contractId={contractId} />
      <p style={{ width: "min(1180px, calc(100% - 40px))", margin: "0 auto 18px" }}>
        <Link href={`/dashboard/disputes?contract=${encodeURIComponent(contractId)}`}>
          Open milestone disputes and evidence →
        </Link>
      </p>
      <p style={{ width: "min(1180px, calc(100% - 40px))", margin: "0 auto 90px" }}>
        <Link href={`/dashboard/messages?contract=${encodeURIComponent(contractId)}`}>
          Open private contract messages →
        </Link>
      </p>
    </>
  );
}
