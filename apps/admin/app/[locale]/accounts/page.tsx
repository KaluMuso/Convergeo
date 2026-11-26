import { adminNavPageMetadata } from "../../../lib/admin-page-metadata";

import { AccountsBoard } from "./accounts-board";

import type { Metadata } from "next";

type PageProps = { params: Promise<{ locale: string }> };

export async function generateMetadata({ params }: PageProps): Promise<Metadata> {
  const { locale } = await params;
  return adminNavPageMetadata(locale, "accounts");
}

export default async function AccountsPage({ params }: PageProps) {
  const { locale } = await params;
  return <AccountsBoard locale={locale} />;
}
