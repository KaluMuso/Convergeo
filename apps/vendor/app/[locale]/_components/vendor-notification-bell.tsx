"use client";

import {
  buildNotificationCopy,
  NotificationBell,
  type NotificationTranslator,
} from "@vergeo/ui/src/notification-center";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useTranslations } from "next-intl";
import { useMemo } from "react";

import { vendorNotificationsApi } from "../../../lib/notifications-client";

export function VendorNotificationBell({ locale }: { locale: string }) {
  const t = useTranslations("notifications") as unknown as NotificationTranslator;
  const router = useRouter();
  const copy = useMemo(() => buildNotificationCopy(t), [t]);
  return (
    <NotificationBell
      api={vendorNotificationsApi()}
      locale={locale}
      labels={copy.labels}
      renderMessage={copy.renderMessage}
      pageHref={`/${locale}/notifications`}
      navigate={(href) => router.push(href)}
      LinkComponent={Link}
    />
  );
}
