import { loadNamespace, type Locale } from "@vergeo/i18n";
import { NextIntlClientProvider, type AbstractIntlMessages } from "next-intl";

import { LazyNotificationBellSlot } from "./lazy-notification-bell-slot";

/**
 * Server wrapper: ships ONLY `notifications.center` + `notifications.inApp`
 * to the client (not the WhatsApp/SMS/email template copy in the same file).
 */
export async function notificationClientMessages(locale: string): Promise<AbstractIntlMessages> {
  const all = (await loadNamespace(locale as Locale, "notifications")) as Record<string, unknown>;
  return { notifications: { center: all.center, inApp: all.inApp } } as AbstractIntlMessages;
}

export async function NotificationBellIsland({ locale }: { locale: string }) {
  const messages = await notificationClientMessages(locale);
  return (
    <NextIntlClientProvider locale={locale} messages={messages}>
      <LazyNotificationBellSlot locale={locale} />
    </NextIntlClientProvider>
  );
}
