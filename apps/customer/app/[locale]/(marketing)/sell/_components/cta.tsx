import Link from "next/link";

import { getVendorLoginUrl } from "./vendor-app";

type PitchTranslator = {
  (key: string, values?: Record<string, string | number>): string;
};

type CtaProps = {
  locale: string;
  t: PitchTranslator;
};

const BUTTON_CLASS =
  "inline-flex h-12 min-h-12 w-full max-w-xs items-center justify-center rounded bg-primary px-6 text-body font-medium text-surface transition-colors duration-fast hover:bg-primary-deep focus-visible:outline-none focus-visible:shadow-focusRing sm:w-auto";

export function Cta({ locale, t }: CtaProps) {
  const loginUrl = getVendorLoginUrl(locale);

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
        <Link className={BUTTON_CLASS} data-testid="vendor-signup-cta" href={loginUrl}>
          {t("cta.button")}
        </Link>
        <p className="text-sm text-text-2">
          <a
            className="font-medium text-primary underline-offset-2 hover:underline"
            data-testid="vendor-cta-invite-signin-link"
            href={loginUrl}
          >
            {t("cta.haveInviteSignIn")}
          </a>
        </p>
      </div>
    </section>
  );
}
