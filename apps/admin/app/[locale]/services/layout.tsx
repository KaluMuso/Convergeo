import type { Metadata } from "next";

import { adminNavPageMetadata } from "../../../lib/admin-page-metadata";

type LayoutProps = { children: React.ReactNode; params: Promise<{ locale: string }> };

export async function generateMetadata({ params }: LayoutProps): Promise<Metadata> {
  const { locale } = await params;
  return adminNavPageMetadata(locale, "services");
}

export default function ServicesLayout({ children }: LayoutProps) {
  return children;
}