import { LOCALES } from "@vergeo/i18n";
import { setRequestLocale } from "next-intl/server";

import { getLegalTranslator, LegalShell } from "../_components/legal-shell";

import type { Metadata } from "next";

const SECTION_IDS = [
  "introduction",
  "commissions",
  "payouts",
  "listing",
  "returns",
  "prohibited",
  "kyc",
  "termination",
  "changes",
  "contact",
] as const;

const COMMISSION_ROWS = [
  { categoryKey: "electronics", rateKey: "electronicsRate" },
  { categoryKey: "homeGoods", rateKey: "homeGoodsRate" },
  { categoryKey: "fashionBeauty", rateKey: "fashionBeautyRate" },
  { categoryKey: "services", rateKey: "servicesRate" },
  { categoryKey: "eventTickets", rateKey: "eventTicketsRate" },
  { categoryKey: "suppliesWholesale", rateKey: "suppliesWholesaleRate" },
  { categoryKey: "groceriesStaples", rateKey: "groceriesStaplesRate" },
  { categoryKey: "defaultCategory", rateKey: "defaultRate" },
  { categoryKey: "freeEvents", rateKey: "freeEventsRate" },
] as const;

const UPDATED_DATE = "7 July 2026";

type PageProps = {
  params: Promise<{ locale: string }>;
};

export function generateStaticParams() {
  return LOCALES.map((locale) => ({ locale }));
}

export async function generateMetadata({ params }: PageProps): Promise<Metadata> {
  const { locale } = await params;
  const t = await getLegalTranslator(locale);

  return {
    title: t("vendorAgreement.title"),
    description: t("vendorAgreement.description"),
    alternates: {
      canonical: `/${locale}/legal/vendor-agreement`,
    },
  };
}

export default async function VendorAgreementPage({ params }: PageProps) {
  const { locale } = await params;
  setRequestLocale(locale);
  const t = await getLegalTranslator(locale);

  const sections = SECTION_IDS.map((id) => ({
    id,
    heading: t(`vendorAgreement.sections.${id}.heading`),
    body: t(`vendorAgreement.sections.${id}.body`),
  }));

  const commissionTable = (
    <section aria-labelledby="commission-table-heading" className="space-y-4">
      <h2 id="commission-table-heading" className="font-display text-h2 text-display-ink">
        {t("vendorAgreement.sections.commissions.heading")}
      </h2>
      <div className="overflow-x-auto rounded-lg border border-border">
        <table className="w-full min-w-[280px] border-collapse text-left text-sm">
          <thead className="bg-bg-2">
            <tr>
              <th className="px-4 py-3 font-semibold text-text" scope="col">
                {t("vendorAgreement.commissions.categoryHeader")}
              </th>
              <th className="px-4 py-3 font-semibold text-text" scope="col">
                {t("vendorAgreement.commissions.rateHeader")}
              </th>
            </tr>
          </thead>
          <tbody>
            {COMMISSION_ROWS.map((row) => (
              <tr key={row.categoryKey} className="border-t border-border">
                <td className="px-4 py-3 text-text">
                  {t(`vendorAgreement.commissions.${row.categoryKey}`)}
                </td>
                <td className="px-4 py-3 font-mono text-text">
                  {t(`vendorAgreement.commissions.${row.rateKey}`)}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <p className="text-sm text-text-2">{t("vendorAgreement.commissions.footnote")}</p>
    </section>
  );

  return (
    <LegalShell
      title={t("vendorAgreement.title")}
      updatedLabel={t("updated", { date: UPDATED_DATE })}
      counselNote={t("counselNote")}
      tocLabel={t("onThisPage")}
      sections={sections}
      afterSections={commissionTable}
    />
  );
}
