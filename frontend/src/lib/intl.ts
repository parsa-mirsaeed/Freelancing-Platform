const DEFAULT_LOCALE = "en-US";

export function currencyFractionDigits(currency: string, locale = DEFAULT_LOCALE): number {
  return new Intl.NumberFormat(locale, {
    style: "currency",
    currency: currency.toUpperCase(),
  }).resolvedOptions().maximumFractionDigits;
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
