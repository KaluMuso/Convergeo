type PitchTranslator = {
  (key: string, values?: Record<string, string | number>): string;
};

type HowItWorksProps = {
  t: PitchTranslator;
};

const STEP_KEYS = ["signup", "kyc", "list", "sell"] as const;

export function HowItWorks({ t }: HowItWorksProps) {
  return (
    <section
      aria-labelledby="how-it-works-heading"
      className="border-y border-border bg-bg-2 px-4 py-10"
    >
      <div className="mx-auto w-full max-w-3xl space-y-6">
        <h2 id="how-it-works-heading" className="font-display text-h2 text-display-ink">
          {t("howItWorks.heading")}
        </h2>
        <ol className="grid grid-cols-1 gap-4 sm:grid-cols-2">
          {STEP_KEYS.map((key, index) => (
            <li key={key} className="rounded-lg border border-border bg-surface p-4 shadow-sm">
              <div className="mb-2 flex items-center gap-3">
                <span
                  aria-hidden
                  className="flex size-8 shrink-0 items-center justify-center rounded-full bg-primary text-sm font-semibold text-surface"
                >
                  {index + 1}
                </span>
                <h3 className="font-semibold text-text">{t(`howItWorks.steps.${key}.title`)}</h3>
              </div>
              <p className="text-sm leading-relaxed text-text-2">
                {t(`howItWorks.steps.${key}.description`)}
              </p>
            </li>
          ))}
        </ol>
      </div>
    </section>
  );
}
