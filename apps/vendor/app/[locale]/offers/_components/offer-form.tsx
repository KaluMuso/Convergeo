"use client";

import { useSession } from "@vergeo/auth/use-session";
import { ApiError } from "@vergeo/config";
import { formatK } from "@vergeo/i18n";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useTranslations } from "next-intl";
import { useCallback, useEffect, useMemo, useState } from "react";

import { ngweeToZmwInput } from "../../listings/[id]/edit/_lib/money";
import { isValidZmwDecimal, zmwDecimalToNgwee } from "../../listings/new/_lib/money";
import { Button, FormField, Input, Select, Spinner } from "../../services/_lib/ui";
import {
  createOffersClient,
  isoToLocalInput,
  localInputToIso,
  OFFER_TYPES,
  TYPE_ROLES,
  type BundlePricing,
  type Offer,
  type OfferItem,
  type OfferItemRole,
  type OfferPayload,
  type OfferPreview,
  type OfferType,
  type PickerOption,
} from "../_lib/offers-client";

type OfferFormProps = {
  locale: string;
  mode: "create" | "edit";
  initialOffer?: Offer;
};

type DraftItem = Pick<OfferItem, "role" | "item_kind" | "ref_id" | "qty">;

function toInt(value: string): number | null {
  const trimmed = value.trim();
  if (!/^\d+$/.test(trimmed)) {
    return null;
  }
  return Number.parseInt(trimmed, 10);
}

export function OfferForm({ locale, mode, initialOffer }: OfferFormProps) {
  const t = useTranslations("vendor.offers");
  const router = useRouter();
  const { session, loading: sessionLoading } = useSession();
  const getToken = useCallback(() => session?.access_token ?? null, [session?.access_token]);
  const api = useMemo(() => createOffersClient(getToken), [getToken]);

  const [offerType, setOfferType] = useState<OfferType>(initialOffer?.offer_type ?? "bundle");
  const [title, setTitle] = useState(initialOffer?.title ?? "");
  const [status, setStatus] = useState<OfferPayload["status"]>(
    initialOffer && initialOffer.status !== "archived" ? initialOffer.status : "draft",
  );
  const [startsAt, setStartsAt] = useState(isoToLocalInput(initialOffer?.starts_at ?? null));
  const [endsAt, setEndsAt] = useState(isoToLocalInput(initialOffer?.ends_at ?? null));
  const [buyQty, setBuyQty] = useState(String(initialOffer?.buy_qty ?? 2));
  const [getQty, setGetQty] = useState(String(initialOffer?.get_qty ?? 1));
  const [bundlePricing, setBundlePricing] = useState<BundlePricing>(
    initialOffer?.bundle_pricing ?? "addon_percent_off",
  );
  const [addonPercent, setAddonPercent] = useState(String(initialOffer?.addon_percent_off ?? 25));
  const [bundlePrice, setBundlePrice] = useState(
    initialOffer?.bundle_price_ngwee ? ngweeToZmwInput(initialOffer.bundle_price_ngwee) : "",
  );
  const [buyN, setBuyN] = useState(String(initialOffer?.buy_n ?? 3));
  const [payM, setPayM] = useState(String(initialOffer?.pay_m ?? 2));
  const [giftStock, setGiftStock] = useState(String(initialOffer?.gift_stock_total ?? 10));
  const [maxApps, setMaxApps] = useState(String(initialOffer?.max_applications_per_order ?? 1));
  const [items, setItems] = useState<DraftItem[]>(
    (initialOffer?.items ?? []).map(({ role, item_kind, ref_id, qty }) => ({
      role,
      item_kind,
      ref_id,
      qty,
    })),
  );
  const [options, setOptions] = useState<PickerOption[] | null>(null);
  const [preview, setPreview] = useState<OfferPreview | null>(null);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (sessionLoading || !session) {
      return;
    }
    let cancelled = false;
    api
      .pickerOptions()
      .then((rows) => {
        if (!cancelled) {
          setOptions(rows);
        }
      })
      .catch(() => {
        if (!cancelled) {
          setOptions([]);
        }
      });
    return () => {
      cancelled = true;
    };
  }, [api, session, sessionLoading]);

  const payload: OfferPayload | null = useMemo(() => {
    const giftTotal = toInt(giftStock);
    let bundlePriceNgwee: number | null = null;
    if (offerType === "bundle" && bundlePricing === "fixed_price") {
      if (!isValidZmwDecimal(bundlePrice)) {
        return null;
      }
      bundlePriceNgwee = zmwDecimalToNgwee(bundlePrice);
    }
    return {
      offer_type: offerType,
      title: title.trim() || t(`types.${offerType}.label`),
      status,
      starts_at: localInputToIso(startsAt),
      ends_at: localInputToIso(endsAt),
      buy_qty: toInt(buyQty),
      get_qty: toInt(getQty),
      bundle_pricing: bundlePricing,
      addon_percent_off: toInt(addonPercent),
      bundle_price_ngwee: bundlePriceNgwee,
      buy_n: toInt(buyN),
      pay_m: toInt(payM),
      gift_stock_total: giftTotal,
      max_applications_per_order: toInt(maxApps) ?? 1,
      items,
    };
  }, [
    addonPercent,
    bundlePrice,
    bundlePricing,
    buyN,
    buyQty,
    endsAt,
    getQty,
    giftStock,
    items,
    maxApps,
    offerType,
    payM,
    startsAt,
    status,
    t,
    title,
  ]);

  // Live "what the customer pays" preview from the same server engine as checkout.
  useEffect(() => {
    if (!payload || !session || items.length === 0) {
      setPreview(null);
      return;
    }
    let cancelled = false;
    const timer = setTimeout(() => {
      api
        .preview(payload)
        .then((result) => {
          if (!cancelled) {
            setPreview(result);
          }
        })
        .catch(() => {
          if (!cancelled) {
            setPreview(null);
          }
        });
    }, 600);
    return () => {
      cancelled = true;
      clearTimeout(timer);
    };
  }, [api, items.length, payload, session]);

  const optionByKey = useMemo(() => {
    const map = new Map<string, PickerOption>();
    for (const option of options ?? []) {
      map.set(`${option.kind}:${option.id}`, option);
    }
    return map;
  }, [options]);

  const addItem = (role: OfferItemRole, key: string) => {
    const option = optionByKey.get(key);
    if (!option) {
      return;
    }
    setItems((current) =>
      current.some((item) => item.role === role && item.ref_id === option.id)
        ? current
        : [...current, { role, item_kind: option.kind, ref_id: option.id, qty: 1 }],
    );
  };

  const removeItem = (role: OfferItemRole, refId: string) =>
    setItems((current) => current.filter((item) => !(item.role === role && item.ref_id === refId)));

  const setItemQty = (role: OfferItemRole, refId: string, qty: number) =>
    setItems((current) =>
      current.map((item) =>
        item.role === role && item.ref_id === refId
          ? { ...item, qty: Math.max(1, Math.min(100, qty)) }
          : item,
      ),
    );

  const onSubmit = async () => {
    if (!payload) {
      setError(t("errors.invalidPrice"));
      return;
    }
    setSaving(true);
    setError(null);
    try {
      if (mode === "create") {
        await api.create(payload);
      } else if (initialOffer) {
        await api.update(initialOffer.id, payload);
      }
      router.push(`/${locale}/offers`);
    } catch (caught) {
      const messageKey = caught instanceof ApiError ? caught.details?.message_key : undefined;
      const key =
        typeof messageKey === "string" ? messageKey.replace(/^vendor\.offers\./, "") : null;
      setError(key && t.has(key) ? t(key) : t("errors.saveFailed"));
    } finally {
      setSaving(false);
    }
  };

  if (sessionLoading) {
    return (
      <div className="flex min-h-[40vh] items-center justify-center">
        <Spinner label={t("loading")} />
      </div>
    );
  }
  if (!session) {
    return <p className="text-sm text-text-2">{t("errors.authRequired")}</p>;
  }

  const editing = mode === "edit";

  return (
    <div className="flex flex-col gap-4">
      <header className="space-y-1">
        <Link href={`/${locale}/offers`} className="text-sm font-medium text-primary">
          {t("backToList")}
        </Link>
        <h1 className="text-xl font-semibold text-text">
          {editing ? t("form.editTitle") : t("form.createTitle")}
        </h1>
      </header>

      {error ? (
        <p className="text-sm text-danger" role="alert">
          {error}
        </p>
      ) : null}

      <fieldset className="flex flex-col gap-2" disabled={editing}>
        <legend className="mb-1 text-sm font-medium text-text">{t("form.typeLabel")}</legend>
        <div className="grid grid-cols-2 gap-2">
          {OFFER_TYPES.map((type) => (
            <label
              key={type}
              className={[
                "flex min-h-11 cursor-pointer flex-col gap-0.5 rounded-md border p-2 text-sm",
                offerType === type ? "border-primary bg-primary-tint" : "border-border bg-surface",
              ].join(" ")}
            >
              <span className="flex items-center gap-2 font-medium text-text">
                <input
                  type="radio"
                  name="offer-type"
                  value={type}
                  checked={offerType === type}
                  onChange={() => {
                    setOfferType(type);
                    setItems([]);
                  }}
                  data-testid={`offer-type-${type}`}
                />
                {t(`types.${type}.label`)}
              </span>
              <span className="text-xs text-text-3">{t(`types.${type}.hint`)}</span>
            </label>
          ))}
        </div>
      </fieldset>

      <FormField id="offer-title" label={t("form.titleLabel")}>
        <Input
          id="offer-title"
          value={title}
          maxLength={120}
          placeholder={t(`types.${offerType}.label`)}
          onChange={(event) => setTitle(event.target.value)}
        />
      </FormField>

      {offerType === "bxgy" ? (
        <div className="grid grid-cols-2 gap-2">
          <FormField id="offer-buy-qty" label={t("form.buyQty")}>
            <Input
              id="offer-buy-qty"
              inputMode="numeric"
              value={buyQty}
              onChange={(e) => setBuyQty(e.target.value)}
            />
          </FormField>
          <FormField id="offer-get-qty" label={t("form.getQty")}>
            <Input
              id="offer-get-qty"
              inputMode="numeric"
              value={getQty}
              onChange={(e) => setGetQty(e.target.value)}
            />
          </FormField>
        </div>
      ) : null}

      {offerType === "bundle" ? (
        <div className="flex flex-col gap-2">
          <FormField id="offer-bundle-pricing" label={t("form.bundlePricing")}>
            <Select
              id="offer-bundle-pricing"
              value={bundlePricing}
              onChange={(event) => setBundlePricing(event.target.value as BundlePricing)}
            >
              <option value="addon_percent_off">{t("form.bundlePercent")}</option>
              <option value="fixed_price">{t("form.bundleFixed")}</option>
            </Select>
          </FormField>
          {bundlePricing === "addon_percent_off" ? (
            <FormField
              id="offer-addon-percent"
              label={t("form.addonPercent")}
              helpText={t("form.addonPercentHint")}
            >
              <Input
                id="offer-addon-percent"
                inputMode="numeric"
                value={addonPercent}
                onChange={(event) => setAddonPercent(event.target.value)}
              />
            </FormField>
          ) : (
            <FormField
              id="offer-bundle-price"
              label={t("form.bundlePrice")}
              helpText={t("form.bundlePriceHint")}
            >
              <Input
                id="offer-bundle-price"
                inputMode="decimal"
                value={bundlePrice}
                onChange={(event) => setBundlePrice(event.target.value)}
              />
            </FormField>
          )}
        </div>
      ) : null}

      {offerType === "buy_n_pay_m" ? (
        <div className="grid grid-cols-2 gap-2">
          <FormField id="offer-buy-n" label={t("form.buyN")}>
            <Input
              id="offer-buy-n"
              inputMode="numeric"
              value={buyN}
              onChange={(e) => setBuyN(e.target.value)}
            />
          </FormField>
          <FormField id="offer-pay-m" label={t("form.payM")}>
            <Input
              id="offer-pay-m"
              inputMode="numeric"
              value={payM}
              onChange={(e) => setPayM(e.target.value)}
            />
          </FormField>
        </div>
      ) : null}

      {offerType === "bxgy" || offerType === "free_gift" ? (
        <FormField
          id="offer-gift-stock"
          label={t("form.giftStock")}
          helpText={
            initialOffer
              ? t("form.giftStockReserved", { reserved: initialOffer.gift_stock_reserved })
              : t("form.giftStockHint")
          }
        >
          <Input
            id="offer-gift-stock"
            inputMode="numeric"
            value={giftStock}
            onChange={(e) => setGiftStock(e.target.value)}
          />
        </FormField>
      ) : null}

      {TYPE_ROLES[offerType].map((spec) => {
        const chosen = items.filter((item) => item.role === spec.role);
        const choices = (options ?? []).filter(
          (option) =>
            spec.kinds.includes(option.kind) && !chosen.some((item) => item.ref_id === option.id),
        );
        return (
          <section
            key={spec.role}
            className="flex flex-col gap-2 rounded-md border border-border p-3"
          >
            <h2 className="text-sm font-semibold text-text">{t(`roles.${spec.role}.label`)}</h2>
            <p className="text-xs text-text-3">{t(`roles.${spec.role}.hint`)}</p>
            <ul className="flex flex-col gap-2">
              {chosen.map((item) => {
                const option = optionByKey.get(`${item.item_kind}:${item.ref_id}`);
                return (
                  <li key={item.ref_id} className="flex items-center justify-between gap-2 text-sm">
                    <span className="min-w-0 flex-1 truncate text-text">
                      {option?.title ?? t("unknownItem")}
                      {option?.price_ngwee ? (
                        <span className="ml-1 font-mono text-text-2">
                          {formatK(option.price_ngwee)}
                        </span>
                      ) : null}
                    </span>
                    {offerType === "bundle" ? (
                      <Input
                        aria-label={t("form.itemQty")}
                        className="w-16"
                        inputMode="numeric"
                        value={String(item.qty)}
                        onChange={(event) =>
                          setItemQty(spec.role, item.ref_id, toInt(event.target.value) ?? 1)
                        }
                      />
                    ) : null}
                    <button
                      type="button"
                      className="min-h-11 px-2 text-sm text-danger"
                      onClick={() => removeItem(spec.role, item.ref_id)}
                    >
                      {t("form.removeItem")}
                    </button>
                  </li>
                );
              })}
            </ul>
            {chosen.length < spec.max ? (
              options === null ? (
                <Spinner label={t("loading")} />
              ) : (
                <Select
                  aria-label={t("form.addItem")}
                  value=""
                  data-testid={`offer-picker-${spec.role}`}
                  onChange={(event) => addItem(spec.role, event.target.value)}
                >
                  <option value="">{t("form.addItem")}</option>
                  {choices.map((option) => (
                    <option
                      key={`${option.kind}:${option.id}`}
                      value={`${option.kind}:${option.id}`}
                    >
                      {t(`kinds.${option.kind}`)} · {option.title}
                    </option>
                  ))}
                </Select>
              )
            ) : null}
          </section>
        );
      })}

      <div className="grid grid-cols-1 gap-2 sm:grid-cols-2">
        <FormField id="offer-starts" label={t("form.startsAt")}>
          <Input
            id="offer-starts"
            type="datetime-local"
            value={startsAt}
            onChange={(e) => setStartsAt(e.target.value)}
          />
        </FormField>
        <FormField id="offer-ends" label={t("form.endsAt")} helpText={t("form.endsAtHint")}>
          <Input
            id="offer-ends"
            type="datetime-local"
            value={endsAt}
            onChange={(e) => setEndsAt(e.target.value)}
          />
        </FormField>
      </div>

      <div className="grid grid-cols-2 gap-2">
        <FormField id="offer-status" label={t("form.status")}>
          <Select
            id="offer-status"
            value={status}
            onChange={(event) => setStatus(event.target.value as OfferPayload["status"])}
          >
            <option value="draft">{t("status.draft")}</option>
            <option value="active">{t("status.active")}</option>
            <option value="paused">{t("status.paused")}</option>
          </Select>
        </FormField>
        <FormField id="offer-max-apps" label={t("form.maxApplications")}>
          <Input
            id="offer-max-apps"
            inputMode="numeric"
            value={maxApps}
            onChange={(e) => setMaxApps(e.target.value)}
          />
        </FormField>
      </div>

      <section
        className="flex flex-col gap-1 rounded-md border border-border bg-bg-2 p-3 text-sm"
        aria-live="polite"
        data-testid="offer-preview"
      >
        <h2 className="text-sm font-semibold text-text">{t("preview.heading")}</h2>
        {preview && preview.applies ? (
          <>
            <p className="m-0 text-text">
              {t("preview.pays", {
                pay: formatK(preview.pay_ngwee),
                list: formatK(preview.list_total_ngwee),
              })}
            </p>
            {preview.savings_ngwee > 0 ? (
              <p className="m-0 font-medium text-success">
                {t("preview.saves", { amount: formatK(preview.savings_ngwee) })}
              </p>
            ) : null}
            {preview.gift_qty > 0 ? (
              <p className="m-0 font-medium text-success">
                {t("preview.gift", {
                  qty: preview.gift_qty,
                  value: formatK(preview.gift_value_ngwee),
                })}
              </p>
            ) : null}
            <p className="m-0 text-xs text-text-3">{t("preview.commissionNote")}</p>
          </>
        ) : (
          <p className="m-0 text-text-2">{t("preview.empty")}</p>
        )}
      </section>

      <Button
        type="button"
        variant="primary"
        disabled={saving || items.length === 0}
        loading={saving}
        loadingLabel={t("form.saving")}
        onClick={() => void onSubmit()}
        data-testid="offer-save"
      >
        {t("form.save")}
      </Button>
    </div>
  );
}
