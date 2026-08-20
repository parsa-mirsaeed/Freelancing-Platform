const DEFAULT_LOCALE = "en-US";

export function currencyFractionDigits(currency: string, locale = DEFAULT_LOCALE): number {
  const fractionDigits = new Intl.NumberFormat(locale, {
    style: "currency",
    currency: currency.toUpperCase(),
  }).resolvedOptions().maximumFractionDigits;
  if (typeof fractionDigits !== "number") {
    throw new RangeError(`Currency fraction metadata is unavailable for ${currency.toUpperCase()}`);
  }
  return fractionDigits;
}

export function formatMinorMoney(
  amountMinor: number,
  currency: string,
  locale = DEFAULT_LOCALE,
): string {
  if (!Number.isSafeInteger(amountMinor)) {
    throw new TypeError("amountMinor must be a safe integer");
  }
  const normalizedCurrency = currency.toUpperCase();
  const fractionDigits = currencyFractionDigits(normalizedCurrency, locale);
  const amountMajor = amountMinor / 10 ** fractionDigits;
  return new Intl.NumberFormat(locale, {
    style: "currency",
    currency: normalizedCurrency,
    currencyDisplay: "narrowSymbol",
  }).format(amountMajor);
}

export function minorMoneyInputValue(amountMinor: number, currency: string): string {
  if (!Number.isSafeInteger(amountMinor) || amountMinor < 0) {
    throw new TypeError("amountMinor must be a non-negative safe integer");
  }
  const fractionDigits = currencyFractionDigits(currency);
  const scale = 10 ** fractionDigits;
  const whole = Math.floor(amountMinor / scale);
  if (fractionDigits === 0) return String(whole);
  return `${whole}.${String(amountMinor % scale).padStart(fractionDigits, "0")}`;
}

export function majorMoneyInputToMinor(value: string, currency: string): number {
  const normalized = value.trim();
  if (!/^\d+(?:\.\d+)?$/.test(normalized)) {
    throw new RangeError("Enter a non-negative amount using digits and an optional decimal point.");
  }
  const fractionDigits = currencyFractionDigits(currency);
  const [wholePart = "0", fractionPart = ""] = normalized.split(".");
  if (fractionPart.length > fractionDigits) {
    throw new RangeError(`${currency.toUpperCase()} supports at most ${fractionDigits} decimal places.`);
  }
  const scale = 10n ** BigInt(fractionDigits);
  const paddedFraction = fractionPart.padEnd(fractionDigits, "0") || "0";
  const minor = BigInt(wholePart) * scale + BigInt(paddedFraction);
  if (minor > BigInt(Number.MAX_SAFE_INTEGER)) {
    throw new RangeError("Amount is too large.");
  }
  return Number(minor);
}

export function formatDateTime(
  value: string | Date,
  locale = DEFAULT_LOCALE,
  timeZone?: string,
): string {
  const date = value instanceof Date ? value : new Date(value);
  if (Number.isNaN(date.getTime())) return "—";
  return new Intl.DateTimeFormat(locale, {
    dateStyle: "medium",
    timeStyle: "short",
    timeZone,
  }).format(date);
}
