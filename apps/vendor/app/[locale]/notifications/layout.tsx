import { loadNamespace, type Locale } from "@vergeo/i18n";

import type { Metadata } from "next";

type LayoutProps = { children: React.ReactNode; params: Promise<{ locale: string }> };

export async function generateMetadata({ params }: LayoutProps): Promise<Metadata> {
  const { locale } = await params;
  const vendorMessages = await loadNamespace(locale as Locale, "vendor");
  const notifications = vendorMessages.settings as {
    notifications: { heading: string };
  };
  return { title: notifications.notifications.heading };
}

export default function NotificationsLayout({ children }: LayoutProps) {
  return children;
}
