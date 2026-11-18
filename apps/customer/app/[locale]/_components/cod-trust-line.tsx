type CodTrustLineProps = {
  /** Localised "You pay on delivery → We deliver → You confirm" line (i18n `codTrust.line`). */
  text: string;
  testId?: string;
};

/**
 * One-line COD trust statement shared by checkout review, order confirmation
 * and the order page so the wording never drifts. Escrow wording ("You paid →
 * Held by Convergeo → Released") is deliberately NOT here: it only belongs on
 * prepaid orders.
 */
export function CodTrustLine({ text, testId = "cod-trust-line" }: CodTrustLineProps) {
  return (
    <p
      className="rounded-card border border-primary/20 bg-primary/5 px-4 py-2.5 font-body text-sm font-medium text-text"
      data-testid={testId}
    >
      {text}
    </p>
  );
}
