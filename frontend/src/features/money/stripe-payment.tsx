"use client";

import { useEffect, useRef, useState } from "react";

import { getPaymentAction } from "@/lib/api/money";

import styles from "./stripe-payment.module.css";

export function StripePayment({
  paymentIntentId,
  onProviderConfirmation,
}: {
  paymentIntentId: string;
  onProviderConfirmation: () => Promise<void>;
}) {
  const onProviderConfirmationRef = useRef(onProviderConfirmation);
  const [redirectUrl, setRedirectUrl] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [message, setMessage] = useState("Preparing secure Stripe Checkout…");

  useEffect(() => {
    onProviderConfirmationRef.current = onProviderConfirmation;
  }, [onProviderConfirmation]);

  useEffect(() => {
    let cancelled = false;

    void getPaymentAction(paymentIntentId)
      .then(async (result) => {
        if (cancelled) return;
        if (!result.action) {
          setMessage("Stripe already reports this payment as complete. Refreshing escrow state…");
          await onProviderConfirmationRef.current();
          return;
        }
        if (result.action.kind !== "redirect" || !result.action.redirect_url) {
          throw new Error(`Unsupported payment action: ${result.action.kind}`);
        }
        setRedirectUrl(result.action.redirect_url);
        setMessage(
          "Continue to Stripe-hosted Checkout. Escrow changes only after the signed provider webhook is processed.",
        );
      })
      .catch((reason: unknown) => {
        if (cancelled) return;
        setError(reason instanceof Error ? reason.message : "Unable to prepare Stripe Checkout.");
        setMessage("");
      });

    return () => {
      cancelled = true;
    };
  }, [paymentIntentId]);

  function continueToStripe() {
    if (!redirectUrl || busy) return;
    setBusy(true);
    setError("");
    try {
      window.location.assign(redirectUrl);
    } catch (reason) {
      setBusy(false);
      setError(reason instanceof Error ? reason.message : "Unable to open Stripe Checkout.");
    }
  }

  return (
    <div className={styles.panel} data-payment-provider="stripe">
      <div className={styles.heading}>
        <strong>Complete Stripe funding</strong>
        <span>Payment details are collected on Stripe-hosted Checkout, not by this application.</span>
      </div>
      {error ? (
        <p className={styles.error} role="alert">
          {error}
        </p>
      ) : null}
      {message ? (
        <p className={styles.note} role="status">
          {message}
        </p>
      ) : null}
      <div className={styles.actions}>
        <button type="button" disabled={!redirectUrl || busy} onClick={continueToStripe}>
          {busy ? "Opening Stripe…" : "Continue to secure checkout"}
        </button>
      </div>
    </div>
  );
}
