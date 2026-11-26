/** Quote statuses where the vendor must not send another quote from the card CTA. */
const TERMINAL_QUOTE_STATUSES = new Set(["submitted", "accepted"]);

export function jobQuoteStatus(ownQuote: { status: string } | null | undefined): string | null {
  return ownQuote?.status ?? null;
}

export function canOpenJobQuoteForm(ownQuote: { status: string } | null | undefined): boolean {
  if (!ownQuote) {
    return true;
  }
  return !TERMINAL_QUOTE_STATUSES.has(ownQuote.status);
}

export function showJobQuoteSummary(ownQuote: { status: string } | null | undefined): boolean {
  return Boolean(ownQuote);
}
