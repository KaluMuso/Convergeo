import Link from "next/link";

import { getVendorSignupUrl } from "./vendor-app";

type PitchTranslator = {
  (key: string, values?: Record<string, string | number>): string;
};

type CtaProps = {
  locale: string;
  t: PitchTranslator;
};

const BUTTON_CLASS =
  "inline-flex h-12 min-h-12 w-full max-w-xs items-center justify-center rounded bg-primary px-6 text-body font-medium text-surface transition-colors duration-fast hover:bg-primary-deep focus-visible:outline-none focus-visible:shadow-focusRing sm:w-auto";

const UNAVAILABLE_BUTTON_CLASS =
  "inline-flex h-12 min-h-12 w-full max-w-xs cursor-not-allowed items-center justify-center rounded bg-primary px-6 text-body font-medium text-surface opacity-60 sm:w-auto";

const UNAVAILABLE_NOTE_ID = "cta-vendor-signup-unavailable";

export function Cta({ locale, t }: CtaProps) {
  const signupUrl = getVendorSignupUrl(locale);

  return (
    <section aria-labelledby="cta-heading" className="border-t border-border bg-bg px-4 py-12">
      <div className="mx-auto w-full max-w-3xl space-y-6 text-center">
        <h2 id="cta-heading" className="font-display text-h2 text-display-ink">
          {t("cta.heading")}
        </h2>
        <p className="text-body text-text-2">{t("cta.body")}</p>
        <p className="text-sm font-medium text-text-2" data-testid="sell-invite-only-notice">
          {t("inviteOnlyNotice")}
        </p>
        {signupUrl ? (
          <Link className={BUTTON_CLASS} data-testid="vendor-signup-cta" href={signupUrl}>
            {t("cta.button")}
          </Link>
        ) : (
          <div className="space-y-2">
            <button
              aria-describedby={UNAVAILABLE_NOTE_ID}
              aria-disabled="true"
              className={UNAVAILABLE_BUTTON_CLASS}
              data-testid="vendor-signup-cta"
              disabled
              type="button"
            >
              {t("cta.button")}
            </button>
            <p id={UNAVAILABLE_NOTE_ID} className="text-sm text-text-3">
              {t("signupUnavailable")}
            </p>
          </div>
        )}
      </div>
    </section>
  );
}
