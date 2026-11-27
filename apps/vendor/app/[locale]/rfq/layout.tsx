import { loadNamespace, type Locale } from "@vergeo/i18n";

import { routeMessagesLayout } from "../_components/route-messages";

import type { Metadata } from "next";

type LayoutProps = { children: React.ReactNode; params: Promise<{ locale: string }> };

export async function generateMetadata({ params }: LayoutProps): Promise<Metadata> {
  const { locale } = await params;
  const vendorMessages = await loadNamespace(locale as Locale, "vendor");
  const rfq = vendorMessages.rfq as { title: string };
  return { title: rfq.title };
}

export default routeMessagesLayout("rfq");
