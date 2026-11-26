import { adminNavPageMetadata } from "../../../lib/admin-page-metadata";

import { AuditLogBoard } from "./audit-log-board";

import type { Metadata } from "next";

type PageProps = { params: Promise<{ locale: string }> };

export async function generateMetadata({ params }: PageProps): Promise<Metadata> {
  const { locale } = await params;
  return adminNavPageMetadata(locale, "auditLog");
}

export default async function AuditLogPage({ params }: PageProps) {
  const { locale } = await params;
  return <AuditLogBoard locale={locale} />;
}
