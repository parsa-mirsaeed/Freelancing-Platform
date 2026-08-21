import { currencyFractionDigits } from "@/lib/intl";

export function majorMoneyToMinor(value: string, currency: string): number | null {
  const normalized = value.trim();
  if (!normalized) return null;
  if (!/^\d+(?:\.\d+)?$/.test(normalized)) {
    throw new TypeError("Enter a non-negative decimal amount.");
  }
  const digits = currencyFractionDigits(currency);
  const [whole = "0", fraction = ""] = normalized.split(".");
  if (fraction.length > digits) {
    throw new RangeError(`${currency.toUpperCase()} supports at most ${digits} decimal places.`);
  }
  const padded = fraction.padEnd(digits, "0");
  const minor = BigInt(whole) * 10n ** BigInt(digits) + BigInt(padded || "0");
  if (minor > BigInt(Number.MAX_SAFE_INTEGER)) {
    throw new RangeError("Amount is too large.");
  }
  return Number(minor);
}

export function minorMoneyToMajor(amountMinor: number | null, currency: string | null): string {
  if (amountMinor === null || !currency) return "";
  const digits = currencyFractionDigits(currency);
  if (digits === 0) return String(amountMinor);
  const base = 10 ** digits;
  const whole = Math.floor(amountMinor / base);
  const fraction = String(amountMinor % base).padStart(digits, "0").replace(/0+$/, "");
  return fraction ? `${whole}.${fraction}` : String(whole);
}
