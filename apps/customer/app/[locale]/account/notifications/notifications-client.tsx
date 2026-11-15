"use client";

import {
  buildNotificationCopy,
  type NotificationTranslator,
} from "@vergeo/ui/src/notification-center";
import { NotificationList } from "@vergeo/ui/src/notification-list";
import { WebPushOptIn } from "@vergeo/ui/src/web-push-opt-in";
import { useRouter } from "next/navigation";
import { useTranslations } from "next-intl";
import { useMemo } from "react";

import {
  customerNotificationsApi,
  customerNotificationsRequest,
} from "../../../../lib/notifications-client";

export function CustomerNotificationsPage({ locale }: { locale: string }) {
  const t = useTranslations("notifications") as unknown as NotificationTranslator;
  const router = useRouter();
  const copy = useMemo(() => buildNotificationCopy(t), [t]);

  return (
    <div>
      <WebPushOptIn
        request={customerNotificationsRequest}
        audience="customer"
        serviceWorkerUrl="/sw.js"
        labels={{
          enable: t("center.push.enable"),
          enabled: t("center.push.enabled"),
          denied: t("center.push.denied"),
          hint: t("center.push.hint"),
          failed: t("center.push.failed"),
        }}
      />
      <NotificationList
        api={customerNotificationsApi()}
        locale={locale}
        labels={copy.labels}
        renderMessage={copy.renderMessage}
        variant="page"
        onNavigate={(href) => router.push(href)}
      />
    </div>
  );
}
