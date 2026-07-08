type PitchTranslator = {
  (key: string, values?: Record<string, string | number>): string;
};

type PayoutPromiseProps = {
  t: PitchTranslator;
};

export function PayoutPromise({ t }: PayoutPromiseProps) {
  return (
    <section
      aria-labelledby="payout-heading"
      className="border-y border-border bg-primary px-4 py-10 text-surface"
    >
      <div className="mx-auto w-full max-w-3xl space-y-3 text-center sm:text-left">
        <h2 id="payout-heading" className="font-display text-h2">
          {t("payout.heading")}
        </h2>
        <p className="text-h3 font-semibold">{t("payout.promise")}</p>
        <p className="text-body leading-relaxed text-surface/90">{t("payout.body")}</p>
      </div>
    </section>
  );
}
