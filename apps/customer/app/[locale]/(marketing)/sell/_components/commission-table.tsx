import { buildCommissionTableRows, COMMISSION_RATES } from "./commission-rates";

type PitchTranslator = {
  (key: string, values?: Record<string, string | number>): string;
};

type CommissionTableProps = {
  t: PitchTranslator;
};

export function CommissionTable({ t }: CommissionTableProps) {
  const rows = buildCommissionTableRows(
    COMMISSION_RATES,
    (categoryKey) => t(`commission.categories.${categoryKey}`),
    (ratePct) => t("commission.rate", { rate: ratePct }),
  );

  return (
    <section id="commissions" aria-labelledby="commission-heading" className="px-4 py-10">
      <div className="mx-auto w-full max-w-3xl space-y-4">
        <header className="space-y-2">
          <h2 id="commission-heading" className="font-display text-h2 text-display-ink">
            {t("commission.heading")}
          </h2>
          <p className="text-body text-text-2">{t("commission.intro")}</p>
        </header>

        <div className="overflow-x-auto rounded-lg border border-border bg-surface">
          <table className="w-full min-w-[280px] text-left text-sm" data-testid="commission-table">
            <thead>
              <tr className="border-b border-border bg-bg-2">
                <th className="px-4 py-3 font-semibold text-text" scope="col">
                  {t("commission.categoryColumn")}
                </th>
                <th className="px-4 py-3 text-right font-semibold text-text" scope="col">
                  {t("commission.rateColumn")}
                </th>
              </tr>
            </thead>
            <tbody>
              {rows.map((row) => (
                <tr
                  key={row.categoryKey}
                  className="border-b border-border last:border-b-0"
                  data-category-key={row.categoryKey}
                >
                  <td className="px-4 py-3 text-text">{row.label}</td>
                  <td className="px-4 py-3 text-right font-mono text-text">{row.rateLabel}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>

        <p className="text-sm text-text-3">{t("commission.footnote")}</p>
      </div>
    </section>
  );
}

export { buildCommissionTableRows, COMMISSION_RATES };
