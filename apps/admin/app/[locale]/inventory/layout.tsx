import { adminNavPageMetadata } from "../../../lib/admin-page-metadata";

import type { Metadata } from "next";

type LayoutProps = { children: React.ReactNode; params: Promise<{ locale: string }> };

export async function generateMetadata({ params }: LayoutProps): Promise<Metadata> {
  const { locale } = await params;
  return adminNavPageMetadata(locale, "inventory");
}

export default function InventoryLayout({ children }: LayoutProps) {
  return children;
}
