import Link from "next/link";

export type QuotaBannerSignup = {
  prompt: string;
  ctaLabel: string;
  href: string;
};

export type QuotaBannerProps = {
  /** Resolved, localised banner message. */
  message: string;
  /** When present (guest-exceeded), render the signup prompt + CTA. */
  signup?: QuotaBannerSignup | null;
};

/**
 * Presentational banner for quota / kill-switch / rate-limit / network states.
 * The parent resolves the `message_key` → localised `message` before rendering,
 * so this component stays free of the i18n provider (easy to unit-test).
 */
export function QuotaBanner({ message, signup = null }: QuotaBannerProps) {
  return (
    <div
      role="status"
      data-testid="ask-quota-banner"
      className="space-y-2 rounded-lg border border-border bg-bg-2 p-3"
    >
      <p className="text-sm text-text-2">{message}</p>
      {signup ? (
        <div className="space-y-1">
          <p className="text-sm text-text-2">{signup.prompt}</p>
          <Link
            href={signup.href}
            data-testid="ask-signup-cta"
            className="inline-flex min-h-11 items-center text-sm font-medium text-primary underline underline-offset-2"
          >
            {signup.ctaLabel}
          </Link>
        </div>
      ) : null}
    </div>
  );
}
