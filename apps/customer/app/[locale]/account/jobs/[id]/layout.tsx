import { buildPageMetadata } from "../../../../../lib/page-title";

import type { Metadata } from "next";
import type { ReactNode } from "react";

export async function generateMetadata({
  params,
}: {
  params: Promise<{ locale: string }>;
}): Promise<Metadata> {
  const { locale } = await params;
  return buildPageMetadata(locale, "services", "quotes.list.title");
}

export default function PageTitleLayout({ children }: { children: ReactNode }) {
  return children;
}
