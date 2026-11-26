import { adminNavPageMetadata } from "../../../lib/admin-page-metadata";

import { RolesBoard } from "./roles-board";

import type { Metadata } from "next";

type PageProps = { params: Promise<{ locale: string }> };

export async function generateMetadata({ params }: PageProps): Promise<Metadata> {
  const { locale } = await params;
  return adminNavPageMetadata(locale, "roles");
}

export default function RolesPage() {
  return <RolesBoard />;
}
