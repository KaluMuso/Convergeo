import { ResetConfirmForm } from "../../../../../../customer/app/[locale]/(auth)/_components/reset-confirm-form";

export default async function AdminResetConfirmPage({
  params,
}: {
  params: Promise<{ locale: string }>;
}) {
  const { locale } = await params;
  return <ResetConfirmForm locale={locale} />;
}
