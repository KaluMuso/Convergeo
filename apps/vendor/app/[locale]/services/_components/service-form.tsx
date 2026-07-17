"use client";

import { useSession } from "@vergeo/auth/use-session";
import { ApiError } from "@vergeo/config";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useTranslations } from "next-intl";
import { useCallback, useMemo, useState } from "react";

import {
  createServicesClient,
  SERVICE_VERTICALS,
  type ServiceStatus,
  type ServiceSummary,
  type ServiceVertical,
} from "../_lib/services-client";
import { Button, FormField, Input, Select, Spinner } from "../_lib/ui";

type ServiceFormProps = {
  locale: string;
  mode: "create" | "edit";
  serviceId?: string;
  initialService?: ServiceSummary;
};

export function ServiceForm({ locale, mode, serviceId, initialService }: ServiceFormProps) {
  const ts = useTranslations("services");
  const router = useRouter();
  const { session, loading: sessionLoading } = useSession();

  const [title, setTitle] = useState(initialService?.title ?? "");
  const [category, setCategory] = useState<ServiceVertical>(
    initialService?.category ?? "home-services",
  );
  const [description, setDescription] = useState(initialService?.description ?? "");
  const [includes, setIncludes] = useState((initialService?.includes ?? []).join("\n"));
  const [serviceArea, setServiceArea] = useState(initialService?.service_area ?? "");
  const [fromPrice, setFromPrice] = useState(
    initialService?.from_price_ngwee ? String(initialService.from_price_ngwee / 100) : "",
  );
  const [bookable, setBookable] = useState(initialService?.bookable ?? false);
  const [bookingPrice, setBookingPrice] = useState(
    initialService?.booking_price_ngwee ? String(initialService.booking_price_ngwee / 100) : "",
  );
  const [status, setStatus] = useState<ServiceStatus>(initialService?.status ?? "draft");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const getToken = useCallback(() => session?.access_token ?? null, [session?.access_token]);
  const servicesClient = useMemo(() => createServicesClient(getToken), [getToken]);

  async function handleSave(nextStatus?: ServiceStatus) {
    if (!title.trim()) {
      return;
    }
    const fromPriceNgwee = fromPrice.trim() ? Math.round(Number.parseFloat(fromPrice) * 100) : null;
    const bookingPriceNgwee = bookingPrice.trim()
      ? Math.round(Number.parseFloat(bookingPrice) * 100)
      : null;

    if (bookable && (bookingPriceNgwee === null || bookingPriceNgwee <= 0)) {
      setError(ts("vendor.errors.bookablePrice"));
      return;
    }

    setSaving(true);
    setError(null);

    const payload = {
      category,
      title: title.trim(),
      description: description.trim() || null,
      service_area: serviceArea.trim() || null,
      from_price_ngwee: fromPriceNgwee,
      bookable,
      booking_price_ngwee: bookingPriceNgwee,
      status: nextStatus ?? status,
      portfolio_images: initialService?.portfolio_images ?? [],
      includes: includes
        .split("\n")
        .map((line) => line.trim())
        .filter((line) => line.length > 0),
    };

    try {
      if (mode === "create") {
        await servicesClient.createService(payload);
        router.push(`/${locale}/services`);
        router.refresh();
        return;
      }
      if (!serviceId) {
        return;
      }
      await servicesClient.updateService(serviceId, payload);
      router.push(`/${locale}/services`);
      router.refresh();
    } catch (err) {
      if (err instanceof ApiError) {
        setError(err.message);
      } else {
        setError(ts("vendor.errors.saveFailed"));
      }
    } finally {
      setSaving(false);
    }
  }

  if (sessionLoading) {
    return (
      <div className="flex min-h-[40vh] items-center justify-center">
        <Spinner label={ts("vendor.form.saving")} />
      </div>
    );
  }

  if (!session) {
    return <p className="text-sm text-text-2">{ts("vendor.errors.authRequired")}</p>;
  }

  return (
    <div className="flex flex-col gap-4">
      <header className="space-y-1">
        <Link href={`/${locale}/services`} className="text-sm font-medium text-primary">
          ← {ts("vendor.list.title")}
        </Link>
        <h1 className="text-xl font-semibold text-text">
          {mode === "create" ? ts("vendor.form.createTitle") : ts("vendor.form.editTitle")}
        </h1>
      </header>

      {error ? <p className="text-sm text-danger">{error}</p> : null}

      <FormField id="title" label={ts("vendor.form.titleLabel")}>
        <Input id="title" value={title} onChange={(event) => setTitle(event.target.value)} />
      </FormField>

      <FormField id="category" label={ts("vendor.form.categoryLabel")}>
        <Select
          id="category"
          value={category}
          onChange={(event) => setCategory(event.target.value as ServiceVertical)}
        >
          {SERVICE_VERTICALS.map((vertical) => (
            <option key={vertical} value={vertical}>
              {ts(`categories.${vertical}`)}
            </option>
          ))}
        </Select>
      </FormField>

      <FormField id="description" label={ts("vendor.form.descriptionLabel")}>
        <textarea
          id="description"
          value={description}
          onChange={(event) => setDescription(event.target.value)}
          rows={4}
          className="w-full rounded-md border border-border bg-surface px-3 py-2 text-sm"
        />
      </FormField>

      <FormField id="includes" label={ts("vendor.form.includesLabel")}>
        <textarea
          id="includes"
          value={includes}
          onChange={(event) => setIncludes(event.target.value)}
          rows={4}
          className="w-full rounded-md border border-border bg-surface px-3 py-2 text-sm"
        />
      </FormField>
      <p className="-mt-2 text-xs text-text-3">{ts("vendor.form.includesHint")}</p>

      <FormField id="service-area" label={ts("vendor.form.areaLabel")}>
        <Input
          id="service-area"
          value={serviceArea}
          onChange={(event) => setServiceArea(event.target.value)}
        />
      </FormField>

      <FormField id="from-price" label={ts("vendor.form.fromPriceLabel")}>
        <Input
          id="from-price"
          inputMode="decimal"
          value={fromPrice}
          onChange={(event) => setFromPrice(event.target.value)}
          placeholder="350"
        />
      </FormField>
      <p className="-mt-2 text-xs text-text-3">{ts("vendor.form.fromPriceHint")}</p>

      <label className="flex items-start gap-2 text-sm text-text">
        <input
          type="checkbox"
          checked={bookable}
          onChange={(event) => setBookable(event.target.checked)}
          className="mt-0.5 h-4 w-4"
        />
        <span>
          <span className="font-medium">{ts("vendor.form.bookableLabel")}</span>
          <span className="block text-xs text-text-3">{ts("vendor.form.bookableHint")}</span>
        </span>
      </label>

      {bookable ? (
        <>
          <FormField id="booking-price" label={ts("vendor.form.bookingPriceLabel")}>
            <Input
              id="booking-price"
              inputMode="decimal"
              value={bookingPrice}
              onChange={(event) => setBookingPrice(event.target.value)}
              placeholder="500"
            />
          </FormField>
          <p className="-mt-2 text-xs text-text-3">{ts("vendor.form.bookingPriceHint")}</p>
        </>
      ) : null}

      <FormField id="status" label={ts("vendor.form.statusLabel")}>
        <Select
          id="status"
          value={status}
          onChange={(event) => setStatus(event.target.value as ServiceStatus)}
        >
          <option value="draft">{ts("vendor.status.draft")}</option>
          <option value="active">{ts("vendor.status.active")}</option>
          <option value="paused">{ts("vendor.status.paused")}</option>
        </Select>
      </FormField>

      <div className="flex flex-col gap-2">
        <Button
          type="button"
          variant="primary"
          disabled={saving}
          loading={saving}
          loadingLabel={ts("vendor.form.saving")}
          onClick={() => handleSave()}
        >
          {saving ? ts("vendor.form.saving") : ts("vendor.form.save")}
        </Button>
        {status !== "active" ? (
          <Button
            type="button"
            variant="secondary"
            disabled={saving}
            loading={saving}
            loadingLabel={ts("vendor.form.saving")}
            onClick={() => handleSave("active")}
          >
            {ts("vendor.form.publish")}
          </Button>
        ) : (
          <Button
            type="button"
            variant="secondary"
            disabled={saving}
            loading={saving}
            loadingLabel={ts("vendor.form.saving")}
            onClick={() => handleSave("paused")}
          >
            {ts("vendor.form.pause")}
          </Button>
        )}
      </div>
    </div>
  );
}
