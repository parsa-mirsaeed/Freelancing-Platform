"use client";

import { useEffect, useRef, useState } from "react";

import { getPaymentAction } from "@/lib/api/money";
import {
  loadStripeBrowser,
  type StripeElements,
  type StripeInstance,
  type StripePaymentElement,
} from "@/lib/stripe-browser";

import styles from "./stripe-payment.module.css";

export function StripePayment({
  paymentIntentId,
  onProviderConfirmation,
}: {
  paymentIntentId: string;
  onProviderConfirmation: () => Promise<void>;
}) {
  const hostRef = useRef<HTMLDivElement | null>(null);
  const stripeRef = useRef<StripeInstance | null>(null);
  const elementsRef = useRef<StripeElements | null>(null);
  const paymentElementRef = useRef<StripePaymentElement | null>(null);
  const [ready, setReady] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [message, setMessage] = useState("Loading secure payment fields…");

  useEffect(() => {
    let cancelled = false;
    const host = hostRef.current;
    if (!host) return;

    void getPaymentAction(paymentIntentId)
      .then(async (result) => {
        if (cancelled) return;
        if (!result.action) {
          setMessage("Provider already reports this payment as complete. Refreshing escrow state…");
          await onProviderConfirmation();
          return;
        }
        if (result.action.kind !== "stripe_payment_intent") {
          throw new Error(`Unsupported payment action: ${result.action.kind}`);
        }

        const Stripe = await loadStripeBrowser();
        if (cancelled) return;
        const stripe = Stripe(result.action.publishable_key);
        const elements = stripe.elements({ clientSecret: result.action.client_secret });
        const paymentElement = elements.create("payment");
        paymentElement.mount(host);
        stripeRef.current = stripe;
        elementsRef.current = elements;
        paymentElementRef.current = paymentElement;
        setMessage("Enter payment details. Escrow changes only after the signed Stripe webhook is processed.");
        setReady(true);
      })
      .catch((reason: unknown) => {
        if (cancelled) return;
        setError(reason instanceof Error ? reason.message : "Unable to initialize Stripe payment.");
        setMessage("");
      });

    return () => {
      cancelled = true;
      paymentElementRef.current?.destroy();
      paymentElementRef.current = null;
      elementsRef.current = null;
      stripeRef.current = null;
    };
  }, [onProviderConfirmation, paymentIntentId]);

  async function confirmPayment() {
    const stripe = stripeRef.current;
    const elements = elementsRef.current;
    if (!stripe || !elements || busy) return;

    setBusy(true);
    setError("");
    try {
      const result = await stripe.confirmPayment({
        elements,
        confirmParams: { return_url: window.location.href },
        redirect: "if_required",
      });
      if (result.error) {
        setError(result.error.message || "Stripe could not confirm the payment.");
        return;
      }
      setMessage(
        result.paymentIntent?.status === "succeeded"
          ? "Stripe confirmed the payment. Waiting for the signed webhook to fund escrow."
          : "Payment submitted. Waiting for Stripe to reach a terminal state.",
      );
      await onProviderConfirmation();
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Unable to confirm Stripe payment.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className={styles.panel} data-payment-provider="stripe">
      <div className={styles.heading}>
        <strong>Complete Stripe funding</strong>
        <span>Card and payment-method details are handled by Stripe.js, not this application.</span>
      </div>
      <div ref={hostRef} className={styles.element} aria-label="Stripe payment details" />
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
        <button type="button" disabled={!ready || busy} onClick={() => void confirmPayment()}>
          {busy ? "Confirming with Stripe…" : "Confirm funding"}
        </button>
      </div>
    </div>
  );
}
