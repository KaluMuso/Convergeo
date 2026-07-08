import Link from "next/link";

type PitchTranslator = {
  (key: string, values?: Record<string, string | number>): string;
};

/** TODO(env): Wire `NEXT_PUBLIC_VENDOR_APP_URL` in the M04-P03 env pass. */
const VENDOR_APP_BASE = process.env.NEXT_PUBLIC_VENDOR_APP_URL ?? "http://localhost:3001";

export const VENDOR_ONBOARDING_PATH = "/onboarding";

export function getVendorSignupUrl(locale: string): string {
  const base = VENDOR_APP_BASE.replace(/\/$/, "");
  return `${base}/${locale}${VENDOR_ONBOARDING_PATH}`;
}

type CtaProps = {
  locale: string;
  t: PitchTranslator;
};

export function Cta({ locale, t }: CtaProps) {
  const signupUrl = getVendorSignupUrl(locale);

  return (
    <section aria-labelledby="cta-heading" className="border-t border-border bg-bg px-4 py-12">
      <div className="mx-auto w-full max-w-3xl space-y-6 text-center">
        <h2 id="cta-heading" className="font-display text-h2 text-display-ink">
          {t("cta.heading")}
        </h2>
        <p className="text-body text-text-2">{t("cta.body")}</p>
        <Link
          className="inline-flex h-12 min-h-12 w-full max-w-xs items-center justify-center rounded bg-primary px-6 text-body font-medium text-surface transition-colors duration-fast hover:bg-primary-deep focus-visible:outline-none focus-visible:shadow-focusRing sm:w-auto"
          data-testid="vendor-signup-cta"
          href={signupUrl}
        >
          {t("cta.button")}
        </Link>
      </div>
    </section>
  );
}
