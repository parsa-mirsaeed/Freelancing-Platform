"use client";

export interface StripePaymentElement {
  mount(target: HTMLElement): void;
  destroy(): void;
}

export interface StripeElements {
  create(type: "payment"): StripePaymentElement;
}

export interface StripePaymentIntentResult {
  status: string;
}

export interface StripeInstance {
  elements(options: { clientSecret: string }): StripeElements;
  confirmPayment(options: {
    elements: StripeElements;
    confirmParams: { return_url: string };
    redirect: "if_required";
  }): Promise<{
    error?: { message?: string };
    paymentIntent?: StripePaymentIntentResult;
  }>;
}

declare global {
  interface Window {
    Stripe?: (publishableKey: string) => StripeInstance;
  }
}

let loader: Promise<(publishableKey: string) => StripeInstance> | null = null;

export function loadStripeBrowser(): Promise<(publishableKey: string) => StripeInstance> {
  if (typeof window === "undefined") {
    return Promise.reject(new Error("Stripe.js is only available in the browser."));
  }
  if (window.Stripe) return Promise.resolve(window.Stripe);
  if (loader) return loader;

  loader = new Promise((resolve, reject) => {
    const finish = () => {
      if (window.Stripe) resolve(window.Stripe);
      else reject(new Error("Stripe.js loaded without exposing the Stripe constructor."));
    };
    const existing = document.querySelector<HTMLScriptElement>("script[data-stripe-platform-js]");
    if (existing) {
      existing.addEventListener("load", finish, { once: true });
      existing.addEventListener(
        "error",
        () => reject(new Error("Unable to load Stripe.js.")),
        { once: true },
      );
      return;
    }

    const script = document.createElement("script");
    script.src = "https://js.stripe.com/dahlia/stripe.js";
    script.async = true;
    script.dataset.stripePlatformJs = "true";
    script.addEventListener("load", finish, { once: true });
    script.addEventListener(
      "error",
      () => reject(new Error("Unable to load Stripe.js.")),
      { once: true },
    );
    document.head.append(script);
  }).catch((reason: unknown) => {
    loader = null;
    throw reason;
  });

  return loader;
}
