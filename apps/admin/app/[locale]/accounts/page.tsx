import { AccountsBoard } from "./accounts-board";

export default async function AccountsPage({ params }: { params: Promise<{ locale: string }> }) {
  const { locale } = await params;
  return <AccountsBoard locale={locale} />;
}
