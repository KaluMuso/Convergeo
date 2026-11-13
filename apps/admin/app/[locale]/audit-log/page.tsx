import { AuditLogBoard } from "./audit-log-board";

export default async function AuditLogPage({ params }: { params: Promise<{ locale: string }> }) {
  const { locale } = await params;
  return <AuditLogBoard locale={locale} />;
}
