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

import { customerNotificationsApi } from "../../../lib/notifications-client";

/** Header bell for signed-in customers; renders nothing for guests. */
export function NotificationBellSlot({ locale }: { locale: string }) {
  const t = useTranslations("notifications") as unknown as NotificationTranslator;
  const router = useRouter();
  const copy = useMemo(() => buildNotificationCopy(t), [t]);
  return (
    <NotificationBell
      api={customerNotificationsApi()}
      locale={locale}
      labels={copy.labels}
      renderMessage={copy.renderMessage}
      pageHref={`/${locale}/account/notifications`}
      navigate={(href) => router.push(href)}
      LinkComponent={Link}
    />
  );
}
