"use client";

import {
  buildNotificationCopy,
  type NotificationTranslator,
} from "@vergeo/ui/src/notification-center";
import { NotificationList } from "@vergeo/ui/src/notification-list";
import { WebPushOptIn } from "@vergeo/ui/src/web-push-opt-in";
import { useParams, useRouter } from "next/navigation";
import { useTranslations } from "next-intl";
import { useMemo } from "react";

import {
  vendorNotificationsApi,
  vendorNotificationsRequest,
} from "../../../lib/notifications-client";

/** Vendor notifications — full paginated list + flag-gated phone alerts. */
export default function VendorNotificationsPage() {
  const { locale } = useParams<{ locale: string }>();
  const t = useTranslations("notifications") as unknown as NotificationTranslator;
  const router = useRouter();
  const copy = useMemo(() => buildNotificationCopy(t), [t]);

  return (
    <main className="mx-auto w-full max-w-3xl px-4 py-6">
      <h1 className="font-display text-h2 text-display-ink">{t("center.title")}</h1>
      <p className="mb-4 mt-1 text-sm text-text-2">{t("center.pageDescription")}</p>
      <WebPushOptIn
        request={vendorNotificationsRequest}
        audience="vendor"
        serviceWorkerUrl="/push-sw.js"
        labels={{
          enable: t("center.push.enable"),
          enabled: t("center.push.enabled"),
          denied: t("center.push.denied"),
          hint: t("center.push.hint"),
          failed: t("center.push.failed"),
        }}
      />
      <NotificationList
        api={vendorNotificationsApi()}
        locale={locale}
        labels={copy.labels}
        renderMessage={copy.renderMessage}
        variant="page"
        onNavigate={(href) => router.push(href)}
      />
    </main>
  );
}
