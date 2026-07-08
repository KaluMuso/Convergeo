type PitchTranslator = {
  (key: string, values?: Record<string, string | number>): string;
};

type KycExplainerProps = {
  t: PitchTranslator;
};

const TIER_KEYS = ["t1", "t2", "t3", "preferred"] as const;

export function KycExplainer({ t }: KycExplainerProps) {
  return (
    <section aria-labelledby="kyc-heading" className="px-4 py-10">
      <div className="mx-auto w-full max-w-3xl space-y-6">
        <header className="space-y-2">
          <h2 id="kyc-heading" className="font-display text-h2 text-display-ink">
            {t("kyc.heading")}
          </h2>
          <p className="text-body text-text-2">{t("kyc.intro")}</p>
        </header>

        <ul className="space-y-4">
          {TIER_KEYS.map((key) => (
            <li key={key} className="rounded-lg border border-border bg-surface p-4 shadow-sm">
              <p className="mb-1 text-micro font-semibold uppercase tracking-wide text-primary">
                {t(`kyc.tiers.${key}.badge`)}
              </p>
              <h3 className="mb-2 font-semibold text-text">{t(`kyc.tiers.${key}.title`)}</h3>
              <p className="text-sm leading-relaxed text-text-2">
                {t(`kyc.tiers.${key}.description`)}
              </p>
            </li>
          ))}
        </ul>
      </div>
    </section>
  );
}
