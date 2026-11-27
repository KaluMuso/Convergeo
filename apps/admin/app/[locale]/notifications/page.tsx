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
import { AdminPageClient } from "../_components/admin-page-client";

/** Admin notifications — KYC submissions and disputes addressed to this admin. */
export default function AdminNotificationsPage() {
  const { locale } = useParams<{ locale: string }>();
  const t = useTranslations("notifications") as unknown as NotificationTranslator;
  const router = useRouter();
  const copy = useMemo(() => buildNotificationCopy(t), [t]);

  return (
    <AdminPageClient title={t("center.title")} subtitle={t("center.pageDescription")}>
      <NotificationList
        api={adminNotificationsApi()}
        locale={locale}
        labels={copy.labels}
        renderMessage={copy.renderMessage}
        variant="page"
        onNavigate={(href) => router.push(href)}
      />
    </AdminPageClient>
  );
}
