"use client";

import { useSession } from "@vergeo/auth/use-session";
import { ApiError, createApiClient } from "@vergeo/config";
import { CouponManager, type CouponManagerLabels } from "@vergeo/ui/src/coupon-manager";
import { useTranslations } from "next-intl";
import { useCallback } from "react";

import { getApiBaseUrl } from "../../../../lib/api-base-url";

function errorKeyOf(error: unknown): string | null {
  if (!(error instanceof ApiError)) return null;
  if (error.code === "feature_disabled") return "disabled";
  const key = error.details.message_key;
  return typeof key === "string" ? (key.split(".").pop() ?? null) : null;
}

export function VendorCoupons({ locale }: { locale: string }) {
  const t = useTranslations("vendor.coupons");
  const { session } = useSession();
  const token = session?.access_token;

  const request = useCallback(
    <T,>(path: string, init?: RequestInit): Promise<T> =>
      createApiClient({ baseUrl: getApiBaseUrl(), getToken: () => token ?? "" }).request<T>(
        path,
        init,
      ),
    [token],
  );

  if (!token) {
    return <p className="text-sm text-text-2">{t("manager.loading")}</p>;
  }
  return (
    <CouponManager
      mode="vendor"
      locale={locale}
      labels={t.raw("manager") as CouponManagerLabels}
      basePath="/vendor/coupons"
      request={request}
      errorKeyOf={errorKeyOf}
    />
  );
}
