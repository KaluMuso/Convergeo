import { loadNamespace, type Locale } from "@vergeo/i18n";
import { setRequestLocale } from "next-intl/server";

import { VendorPage } from "../../../../_components/vendor-page";
import { AddBranchForm } from "../../../_components/add-branch-form";

import type { Metadata } from "next";

/**
 * Protected, per-business route — `businessId` is an arbitrary UUID, so no
 * generateStaticParams() can be correct (see protected-dynamic-routes.test.ts).
 */
export const dynamic = "force-dynamic";

type PageProps = { params: Promise<{ locale: string; businessId: string }> };

export async function generateMetadata({ params }: PageProps): Promise<Metadata> {
  const { locale } = await params;
  const vendor = await loadNamespace(locale as Locale, "vendor");
  const branches = vendor.branches as { form: { title: string } };
  return { title: branches.form.title, robots: { index: false, follow: false } };
}

export default async function NewBranchPage({ params }: PageProps) {
  const { locale, businessId } = await params;
  setRequestLocale(locale);
  const vendor = await loadNamespace(locale as Locale, "vendor");
  const branches = vendor.branches as { form: { title: string; intro: string } };
  return (
    <VendorPage width="form">
      <header className="space-y-1">
        <h1 className="m-0 font-display text-h1 font-bold text-display-ink">
          {branches.form.title}
        </h1>
        <p className="m-0 text-sm text-text-2">{branches.form.intro}</p>
      </header>
      <AddBranchForm locale={locale} businessId={businessId} />
    </VendorPage>
  );
}
