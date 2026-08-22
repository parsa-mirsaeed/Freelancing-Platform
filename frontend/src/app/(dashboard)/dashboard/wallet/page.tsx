import type { Metadata } from "next";

import { WalletWorkspace } from "@/features/money/wallet-workspace";

export const metadata: Metadata = {
  title: "Wallet & payouts",
  description: "Review ledger-derived freelancer balances and request backend-authoritative payouts.",
};

export default function DashboardWalletPage() {
  return <WalletWorkspace />;
}
