"use client";

import {
  buildNotificationCopy,
  type NotificationTranslator,
} from "@vergeo/ui/src/notification-center";
import { NotificationList } from "@vergeo/ui/src/notification-list";
import { useParams, useRouter } from "next/navigation";
import { useTranslations } from "next-intl";
import { useMemo } from "react";

import { adminNotificationsApi } from "../../../lib/notifications-client";

/** Admin notifications — KYC submissions and disputes addressed to this admin. */
export default function AdminNotificationsPage() {
  const { locale } = useParams<{ locale: string }>();
  const t = useTranslations("notifications") as unknown as NotificationTranslator;
  const router = useRouter();
  const copy = useMemo(() => buildNotificationCopy(t), [t]);

  return (
    <section className="space-y-4">
      <div>
        <h2 className="font-serif text-xl text-text">{t("center.title")}</h2>
        <p className="mt-1 text-sm text-muted">{t("center.pageDescription")}</p>
      </div>
      <NotificationList
        api={adminNotificationsApi()}
        locale={locale}
        labels={copy.labels}
        renderMessage={copy.renderMessage}
        variant="page"
        onNavigate={(href) => router.push(href)}
      />
    </section>
  );
}
