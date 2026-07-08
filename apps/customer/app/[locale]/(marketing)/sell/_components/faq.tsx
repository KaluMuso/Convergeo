type PitchTranslator = {
  (key: string, values?: Record<string, string | number>): string;
};

type FaqProps = {
  t: PitchTranslator;
};

const FAQ_KEYS = ["fees", "payout", "whatCanISell", "kyc"] as const;

export function Faq({ t }: FaqProps) {
  return (
    <section aria-labelledby="faq-heading" className="px-4 py-10">
      <div className="mx-auto w-full max-w-3xl space-y-6">
        <h2 id="faq-heading" className="font-display text-h2 text-display-ink">
          {t("faq.heading")}
        </h2>
        <dl className="space-y-4">
          {FAQ_KEYS.map((key) => (
            <div key={key} className="rounded-lg border border-border bg-surface p-4 shadow-sm">
              <dt className="mb-2 font-semibold text-text">{t(`faq.items.${key}.question`)}</dt>
              <dd className="text-sm leading-relaxed text-text-2">
                {t(`faq.items.${key}.answer`)}
              </dd>
            </div>
          ))}
        </dl>
      </div>
    </section>
  );
}

export { FAQ_KEYS };
