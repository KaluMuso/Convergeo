import { adminNavPageMetadata } from "../../../lib/admin-page-metadata";

import { AdminCoupons } from "./admin-coupons";

import type { Metadata } from "next";

type MetaProps = { params: Promise<{ locale: string }> };

export async function generateMetadata({ params }: MetaProps): Promise<Metadata> {
  const { locale } = await params;
  return adminNavPageMetadata(locale, "coupons");
}

export default function CouponsPage() {
  return <AdminCoupons />;
}
