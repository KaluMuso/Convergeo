"use client";

import { useSession } from "@vergeo/auth/use-session";
import { createApiClient } from "@vergeo/config";
import { useLocale, useTranslations } from "next-intl";
import { useEffect, useMemo, useState } from "react";

import { getApiBaseUrl } from "../../../lib/api-base-url";

type TrialStatus = { in_trial?: boolean; trial_ends_at?: string | null };

/** "Free Business plan until 15 Jan 2027" — formatted in the vendor's locale, Lusaka time. */
export function formatTrialEnd(iso: string, locale: string): string | null {
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return null;
  return new Intl.DateTimeFormat(locale, {
    day: "numeric",
    month: "short",
    year: "numeric",
    timeZone: "Africa/Lusaka",
  }).format(date);
}

/**
 * Pilot free-trial banner: every seller pays no plan fee until the trial ends.
 * Hidden when not in trial or when the status cannot be read.
 */
export function TrialBanner() {
  const t = useTranslations("vendor.trial");
  const locale = useLocale();
  const { session } = useSession();
  const token = session?.access_token ?? null;
  const client = useMemo(
    () => createApiClient({ baseUrl: getApiBaseUrl(), getToken: () => token }),
    [token],
  );
  const [until, setUntil] = useState<string | null>(null);

  useEffect(() => {
    if (!token) return;
    let cancelled = false;
    client
      .request<TrialStatus>("/vendor/plan")
      .then((status) => {
        if (cancelled || !status.in_trial || !status.trial_ends_at) return;
        setUntil(formatTrialEnd(status.trial_ends_at, locale));
      })
      .catch(() => undefined);
    return () => {
      cancelled = true;
    };
  }, [client, locale, token]);

  if (!until) return null;
  return (
    <p
      role="status"
      data-testid="vendor-trial-banner"
      className="m-0 border-b border-border bg-primary-tint px-4 py-2 text-sm text-text"
    >
      <span className="font-semibold">{t("banner", { date: until })}</span>{" "}
      <span className="text-text-2">{t("detail")}</span>
    </p>
  );
}
