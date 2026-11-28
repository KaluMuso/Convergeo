import { adminNavPageMetadata } from "../../../lib/admin-page-metadata";
import { OversightList } from "../_components/oversight-list";

import type { Metadata } from "next";

type MetaProps = { params: Promise<{ locale: string }> };

export async function generateMetadata({ params }: MetaProps): Promise<Metadata> {
  const { locale } = await params;
  return adminNavPageMetadata(locale, "inventory");
}

export default function InventoryPage() {
  return <OversightList kind="inventory" />;
}
