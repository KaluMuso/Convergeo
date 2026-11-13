"use client";

import { ApiError } from "@vergeo/config";
import { CouponManager, type CouponManagerLabels } from "@vergeo/ui/src/coupon-manager";
import { useLocale, useTranslations } from "next-intl";
import { useCallback } from "react";

import { rolesApi } from "../../../lib/roles-api";

function errorKeyOf(error: unknown): string | null {
  if (!(error instanceof ApiError)) return null;
  if (error.code === "feature_disabled") return "disabled";
  if (error.code === "forbidden") return "forbidden";
  const key = error.details.message_key;
  return typeof key === "string" ? (key.split(".").pop() ?? null) : null;
}

/** Platform-funded coupons (paid from the monthly promotions budget). */
export function AdminCoupons() {
  const t = useTranslations("admin.coupons");
  const locale = useLocale();
  const request = useCallback(
    <T,>(path: string, init?: RequestInit): Promise<T> => rolesApi.request<T>(path, init),
    [],
  );
  return (
    <main className="mx-auto w-full max-w-3xl p-4">
      <CouponManager
        mode="platform"
        locale={locale}
        labels={t.raw("manager") as CouponManagerLabels}
        basePath="/admin/coupons"
        request={request}
        errorKeyOf={errorKeyOf}
      />
    </main>
  );
}
