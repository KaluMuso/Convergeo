import { Pill } from "@vergeo/ui/src/pill";
import { tokens } from "@vergeo/ui/tokens";
import Link from "next/link";

import { getVendorSignupUrl } from "./cta";

type PitchTranslator = {
  (key: string, values?: Record<string, string | number>): string;
};

type HeroProps = {
  locale: string;
  t: PitchTranslator;
};

const VERTICAL_KEYS = ["products", "services", "events", "supplies", "directory"] as const;

const VERTICAL_COLORS: Record<(typeof VERTICAL_KEYS)[number], string> = {
  products: tokens.colors.catHome,
  services: tokens.colors.catFitness,
  events: tokens.colors.catBeauty,
  supplies: tokens.colors.catAuto,
  directory: tokens.colors.catHealth,
};

export function Hero({ locale, t }: HeroProps) {
  const signupUrl = getVendorSignupUrl(locale);

  return (
    <section
      aria-labelledby="sell-hero-heading"
      className="border-b border-border bg-bg px-4 py-10 sm:py-14"
    >
      <div className="mx-auto w-full max-w-3xl space-y-8">
        <div className="space-y-4 text-center sm:text-left">
          <p className="text-micro font-semibold uppercase tracking-wide text-primary">
            {t("hero.eyebrow")}
          </p>
          <h1 id="sell-hero-heading" className="font-display text-hero text-display-ink">
            {t("hero.headline")}{" "}
            <em className="not-italic text-primary">{t("hero.headlineEmphasis")}</em>
          </h1>
          <p className="text-body leading-relaxed text-text-2">{t("hero.subheadline")}</p>
          <p className="text-sm text-text-3">{t("hero.freeTierNote")}</p>
        </div>

        <div className="flex flex-col gap-3 sm:flex-row sm:items-center">
          <Link
            className="inline-flex h-12 min-h-12 items-center justify-center rounded bg-primary px-6 text-body font-medium text-surface transition-colors duration-fast hover:bg-primary-deep focus-visible:outline-none focus-visible:shadow-focusRing"
            href={signupUrl}
          >
            {t("hero.primaryCta")}
          </Link>
          <a
            className="inline-flex h-12 min-h-12 items-center justify-center rounded border border-border bg-surface px-6 text-body font-medium text-text transition-colors duration-fast hover:bg-bg-2 focus-visible:outline-none focus-visible:shadow-focusRing"
            href="#commissions"
          >
            {t("hero.secondaryCta")}
          </a>
        </div>

        <div className="space-y-4">
          <h2 className="text-sm font-semibold uppercase tracking-wide text-text-2">
            {t("valueProps.heading")}
          </h2>
          <ul className="grid grid-cols-1 gap-3 sm:grid-cols-2">
            {VERTICAL_KEYS.map((key) => (
              <li key={key} className="rounded-lg border border-border bg-surface p-4 shadow-sm">
                <div className="mb-2">
                  <Pill color={VERTICAL_COLORS[key]} label={t(`valueProps.${key}.title`)} />
                </div>
                <p className="text-sm leading-relaxed text-text-2">
                  {t(`valueProps.${key}.description`)}
                </p>
              </li>
            ))}
          </ul>
        </div>
      </div>
    </section>
  );
}
