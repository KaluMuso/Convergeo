"use client";

import { useRouter } from "next/navigation";
import { useTranslations } from "next-intl";
import { useState } from "react";

import { type OrderSearchItem, ordersApi } from "./api";

type OrderSearchProps = {
  locale: string;
};

export function OrderSearch({ locale }: OrderSearchProps) {
  const t = useTranslations("admin.orders.search");
  const router = useRouter();
  const [orderId, setOrderId] = useState("");
  const [phone, setPhone] = useState("");
  const [vendor, setVendor] = useState("");
  const [status, setStatus] = useState("");
  const [results, setResults] = useState<OrderSearchItem[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [searched, setSearched] = useState(false);

  const runSearch = async () => {
    if (!orderId && !phone && !vendor && !status) {
      setError(t("needFilter"));
      return;
    }
    setLoading(true);
    setError(null);
    setSearched(true);
    try {
      const params = new URLSearchParams();
      if (orderId.trim()) params.set("order_id", orderId.trim());
      if (phone.trim()) params.set("phone", phone.trim());
      if (vendor.trim()) params.set("vendor", vendor.trim());
      if (status.trim()) params.set("status", status.trim());
      const data = await ordersApi.request<OrderSearchItem[]>(
        `/admin/orders/search?${params.toString()}`,
      );
      setResults(data);
    } catch {
      setError(t("error"));
      setResults([]);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="space-y-4">
      <form
        className="grid gap-3 sm:grid-cols-2"
        onSubmit={(event) => {
          event.preventDefault();
          void runSearch();
        }}
      >
        <label className="space-y-1 text-sm">
          <span className="text-[#6B5E4C]">{t("orderId")}</span>
          <input
            className="min-h-11 w-full rounded-md border border-[#E8DFD0] px-3"
            value={orderId}
            onChange={(event) => setOrderId(event.target.value)}
            placeholder={t("orderIdPlaceholder")}
          />
        </label>
        <label className="space-y-1 text-sm">
          <span className="text-[#6B5E4C]">{t("phone")}</span>
          <input
            className="min-h-11 w-full rounded-md border border-[#E8DFD0] px-3"
            value={phone}
            onChange={(event) => setPhone(event.target.value)}
            placeholder={t("phonePlaceholder")}
          />
        </label>
        <label className="space-y-1 text-sm">
          <span className="text-[#6B5E4C]">{t("vendor")}</span>
          <input
            className="min-h-11 w-full rounded-md border border-[#E8DFD0] px-3"
            value={vendor}
            onChange={(event) => setVendor(event.target.value)}
            placeholder={t("vendorPlaceholder")}
          />
        </label>
        <label className="space-y-1 text-sm">
          <span className="text-[#6B5E4C]">{t("status")}</span>
          <select
            className="min-h-11 w-full rounded-md border border-[#E8DFD0] px-3"
            value={status}
            onChange={(event) => setStatus(event.target.value)}
          >
            <option value="">{t("statusAny")}</option>
            {(
              [
                "placed",
                "confirmed",
                "processing",
                "ready",
                "shipped",
                "delivered",
                "completed",
                "cancelled",
              ] as const
            ).map((value) => (
              <option key={value} value={value}>
                {t(`statuses.${value}`)}
              </option>
            ))}
          </select>
        </label>
        <div className="sm:col-span-2">
          <button
            type="submit"
            className="inline-flex min-h-11 items-center rounded-md bg-[#2D4A7A] px-4 text-sm font-medium text-white"
            disabled={loading}
          >
            {loading ? t("searching") : t("submit")}
          </button>
        </div>
      </form>

      {error ? <p className="text-sm text-[#9B2C2C]">{error}</p> : null}

      {searched && !loading && results.length === 0 ? (
        <p className="text-sm text-[#6B5E4C]">{t("empty")}</p>
      ) : null}

      {results.length > 0 ? (
        <div className="overflow-x-auto">
          <table className="min-w-full text-left text-sm">
            <thead>
              <tr className="border-b border-[#E8DFD0] text-xs uppercase tracking-wide text-[#6B5E4C]">
                <th className="px-2 py-3 font-medium">{t("columns.order")}</th>
                <th className="px-2 py-3 font-medium">{t("columns.vendor")}</th>
                <th className="px-2 py-3 font-medium">{t("columns.phone")}</th>
                <th className="px-2 py-3 font-medium">{t("columns.status")}</th>
                <th className="px-2 py-3 font-medium" />
              </tr>
            </thead>
            <tbody>
              {results.map((item) => (
                <tr key={item.id} className="border-b border-[#F0E9DE]">
                  <td className="px-2 py-3 font-mono text-xs">{item.id}</td>
                  <td className="px-2 py-3">
                    <div className="font-medium">{item.vendor_display_name}</div>
                    <div className="text-xs text-[#6B5E4C]">{item.vendor_slug}</div>
                  </td>
                  <td className="px-2 py-3 text-[#6B5E4C]">{item.customer_phone ?? "—"}</td>
                  <td className="px-2 py-3">{t(`statuses.${item.status}`)}</td>
                  <td className="px-2 py-3 text-right">
                    <button
                      type="button"
                      className="inline-flex min-h-11 items-center rounded-md border border-[#2D4A7A] px-4 text-sm font-medium text-[#2D4A7A]"
                      onClick={() => router.push(`/${locale}/orders/${item.id}`)}
                    >
                      {t("open")}
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : null}
    </div>
  );
}
