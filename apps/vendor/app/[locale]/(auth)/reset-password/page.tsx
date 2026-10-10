import { ResetRequestForm } from "../../../../../customer/app/[locale]/(auth)/_components/reset-request-form";

export default async function VendorResetPage({ params }: { params: Promise<{ locale: string }> }) {
  const { locale } = await params;
  return <ResetRequestForm locale={locale} />;
}
