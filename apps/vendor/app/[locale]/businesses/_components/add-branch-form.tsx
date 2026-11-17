"use client";

import { useSession } from "@vergeo/auth/use-session";
import { formatK } from "@vergeo/i18n";
import { Button } from "@vergeo/ui/src/button";
import { Input } from "@vergeo/ui/src/input";
import { Select } from "@vergeo/ui/src/select";
import { useRouter } from "next/navigation";
import { useTranslations } from "next-intl";
import { useEffect, useMemo, useState } from "react";

import { branchErrorKey, tooCloseValues } from "../_lib/branch-errors";
import {
  createBusinessesClient,
  type Business,
  type BranchCreatePayload,
} from "../_lib/businesses-client";

type Props = { locale: string; businessId: string };

const DAYS = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"] as const;

/** Lusaka-first defaults; any valid point inside Zambia is accepted by the API. */
export function buildBranchPayload(form: {
  name: string;
  kind: "physical" | "online";
  lat: string;
  lng: string;
  landmark: string;
  address: string;
  mapUrl: string;
  phone: string;
  email: string;
  whatsapp: string;
  payout: string;
  rail: "mtn" | "airtel" | "zamtel";
  open: string;
  close: string;
  sundayClosed: boolean;
}): BranchCreatePayload {
  const hours: BranchCreatePayload["hours"] = {};
  for (const day of DAYS) {
    hours[day] =
      day === "sun" && form.sundayClosed
        ? { closed: true }
        : { open: form.open, close: form.close };
  }
  const payload: BranchCreatePayload = {
    display_name: form.name.trim(),
    branch_kind: form.kind,
    hours,
    contact_phone: form.phone.trim(),
    payout_msisdn: form.payout.trim(),
    payout_rail: form.rail,
  };
  if (form.email.trim()) payload.contact_email = form.email.trim();
  if (form.whatsapp.trim()) payload.whatsapp_msisdn = form.whatsapp.trim();
  if (form.kind === "physical") {
    payload.location = {
      lat: Number(form.lat),
      lng: Number(form.lng),
      landmark: form.landmark.trim(),
      ...(form.address.trim() ? { address: form.address.trim() } : {}),
      ...(form.mapUrl.trim() ? { map_url: form.mapUrl.trim() } : {}),
    };
  }
  return payload;
}

export function AddBranchForm({ locale, businessId }: Props) {
  const t = useTranslations("vendor.branches");
  const router = useRouter();
  const { session } = useSession();
  const token = session?.access_token ?? null;
  const client = useMemo(() => createBusinessesClient(() => token), [token]);
  const [business, setBusiness] = useState<Business | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [errorValues, setErrorValues] = useState<Record<string, number>>({});
  const [form, setForm] = useState({
    name: "",
    kind: "physical" as "physical" | "online",
    lat: "",
    lng: "",
    landmark: "",
    address: "",
    mapUrl: "",
    phone: "",
    email: "",
    whatsapp: "",
    payout: "",
    rail: "mtn" as "mtn" | "airtel" | "zamtel",
    open: "08:00",
    close: "18:00",
    sundayClosed: true,
  });

  useEffect(() => {
    if (!token) return;
    client
      .list()
      .then((data) => setBusiness(data.businesses.find((b) => b.id === businessId) ?? null))
      .catch(() => setBusiness(null));
  }, [businessId, client, token]);

  const set = <K extends keyof typeof form>(key: K, value: (typeof form)[K]) =>
    setForm((prev) => ({ ...prev, [key]: value }));

  const useMyLocation = () => {
    if (!("geolocation" in navigator)) return;
    navigator.geolocation.getCurrentPosition(
      (pos) => {
        set("lat", pos.coords.latitude.toFixed(6));
        set("lng", pos.coords.longitude.toFixed(6));
      },
      () => setError("branches.errors.locationDenied"),
      { enableHighAccuracy: true, timeout: 10_000 },
    );
  };

  const submit = async (event: React.FormEvent) => {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await client.createBranch(businessId, buildBranchPayload(form));
      router.push(`/${locale}/businesses`);
    } catch (err) {
      const close = tooCloseValues(err);
      setErrorValues(close ? { min: close.min, nearest: close.nearest } : {});
      setError(branchErrorKey(err));
    } finally {
      setBusy(false);
    }
  };

  const allowance = business?.allowance;
  const price =
    allowance && allowance.next_billing_role === "addon" && allowance.next_price_ngwee !== null
      ? t("form.priceAddon", { price: formatK(allowance.next_price_ngwee) })
      : t("form.priceIncluded");

  const field = (label: string, input: React.ReactNode, help?: string) => (
    <label className="flex flex-col gap-1 text-sm">
      <span className="font-medium text-text">{label}</span>
      {input}
      {help ? <span className="text-micro text-text-2">{help}</span> : null}
    </label>
  );

  return (
    <form className="space-y-4" onSubmit={(event) => void submit(event)} noValidate>
      {allowance && !allowance.can_add ? (
        <p role="alert" className="m-0 text-sm text-danger">
          {t(
            allowance.blocked_reason === "unregistered"
              ? "allowance.blockedUnregistered"
              : "allowance.blockedPlan",
          )}
        </p>
      ) : (
        <p className="m-0 rounded bg-primary-tint p-3 text-sm text-text">{price}</p>
      )}

      <fieldset className="space-y-3 border-0 p-0">
        <legend className="mb-2 font-display text-h3 text-display-ink">{t("form.shop")}</legend>
        {field(
          t("form.name"),
          <Input
            required
            maxLength={80}
            value={form.name}
            onChange={(e) => set("name", e.target.value)}
          />,
        )}
        {field(
          t("form.kind"),
          <Select
            value={form.kind}
            onChange={(e) => set("kind", e.target.value as "physical" | "online")}
          >
            <option value="physical">{t("form.kindPhysical")}</option>
            <option value="online">{t("form.kindOnline")}</option>
          </Select>,
        )}
      </fieldset>

      {form.kind === "physical" ? (
        <fieldset className="space-y-3 border-0 p-0">
          <legend className="mb-2 font-display text-h3 text-display-ink">
            {t("form.location")}
          </legend>
          <Button
            type="button"
            size="sm"
            variant="secondary"
            onClick={useMyLocation}
            loadingLabel={t("actions.saving")}
          >
            {t("form.useMyLocation")}
          </Button>
          <div className="grid grid-cols-2 gap-2">
            {field(
              t("form.lat"),
              <Input
                inputMode="decimal"
                value={form.lat}
                onChange={(e) => set("lat", e.target.value)}
              />,
            )}
            {field(
              t("form.lng"),
              <Input
                inputMode="decimal"
                value={form.lng}
                onChange={(e) => set("lng", e.target.value)}
              />,
            )}
          </div>
          {field(
            t("form.landmark"),
            <Input
              maxLength={200}
              value={form.landmark}
              onChange={(e) => set("landmark", e.target.value)}
            />,
            t("form.landmarkHelp"),
          )}
          {field(
            t("form.address"),
            <Input
              maxLength={300}
              value={form.address}
              onChange={(e) => set("address", e.target.value)}
            />,
          )}
          {field(
            t("form.mapUrl"),
            <Input
              type="url"
              maxLength={500}
              value={form.mapUrl}
              onChange={(e) => set("mapUrl", e.target.value)}
            />,
          )}
          <div className="grid grid-cols-2 gap-2">
            {field(
              t("form.opens"),
              <Input type="time" value={form.open} onChange={(e) => set("open", e.target.value)} />,
            )}
            {field(
              t("form.closes"),
              <Input
                type="time"
                value={form.close}
                onChange={(e) => set("close", e.target.value)}
              />,
            )}
          </div>
          <label className="flex items-center gap-2 text-sm text-text">
            <input
              type="checkbox"
              checked={form.sundayClosed}
              onChange={(e) => set("sundayClosed", e.target.checked)}
            />
            {t("form.sundayClosed")}
          </label>
        </fieldset>
      ) : null}

      <fieldset className="space-y-3 border-0 p-0">
        <legend className="mb-2 font-display text-h3 text-display-ink">{t("form.contacts")}</legend>
        {field(
          t("form.phone"),
          <Input
            type="tel"
            inputMode="tel"
            value={form.phone}
            onChange={(e) => set("phone", e.target.value)}
          />,
        )}
        {field(
          t("form.whatsapp"),
          <Input
            type="tel"
            inputMode="tel"
            value={form.whatsapp}
            onChange={(e) => set("whatsapp", e.target.value)}
          />,
        )}
        {field(
          t("form.email"),
          <Input type="email" value={form.email} onChange={(e) => set("email", e.target.value)} />,
        )}
      </fieldset>

      <fieldset className="space-y-3 border-0 p-0">
        <legend className="mb-2 font-display text-h3 text-display-ink">{t("form.payout")}</legend>
        {field(
          t("form.payoutNumber"),
          <Input
            type="tel"
            inputMode="tel"
            value={form.payout}
            onChange={(e) => set("payout", e.target.value)}
          />,
          t("form.payoutHelp"),
        )}
        {field(
          t("form.rail"),
          <Select
            value={form.rail}
            onChange={(e) => set("rail", e.target.value as "mtn" | "airtel" | "zamtel")}
          >
            <option value="mtn">{t("form.rails.mtn")}</option>
            <option value="airtel">{t("form.rails.airtel")}</option>
            <option value="zamtel">{t("form.rails.zamtel")}</option>
          </Select>,
        )}
      </fieldset>

      <p className="m-0 text-sm text-text-2">{t("form.reviewNote")}</p>
      {error ? (
        <p role="alert" className="m-0 text-sm text-danger">
          {t(error.replace(/^branches\./, ""), errorValues)}
        </p>
      ) : null}
      <Button
        type="submit"
        loading={busy}
        loadingLabel={t("actions.saving")}
        disabled={busy || (allowance ? !allowance.can_add : false)}
      >
        {t("actions.createShop")}
      </Button>
    </form>
  );
}
