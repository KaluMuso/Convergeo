"use client";

import { useSession } from "@vergeo/auth/use-session";
import { ApiError } from "@vergeo/config";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useTranslations } from "next-intl";
import { useCallback, useLayoutEffect, useMemo, useRef, useState } from "react";

import { EventImagePicker } from "../../events/_components/image-picker";
import { ngweeToZmwInput } from "../../listings/[id]/edit/_lib/money";
import { isValidZmwDecimal, zmwDecimalToNgwee } from "../../listings/new/_lib/money";
import {
  ARCHETYPES,
  attributesFromValues,
  effectiveArchetype,
  SERVICE_FIELDS,
  valuesFromAttributes,
  type AttributeErrors,
  type FieldValues,
} from "../_lib/archetypes";
import {
  createServicesClient,
  SERVICE_VERTICALS,
  type ServiceStatus,
  type ServiceSummary,
  type ServiceVertical,
} from "../_lib/services-client";
import { Button, FormField, Input, Select, Spinner } from "../_lib/ui";

import { AttributeFields } from "./attribute-fields";

/** Every service field definition, so values saved under any archetype load once. */
const ALL_SERVICE_DEFS = Array.from(
  new Map(
    ARCHETYPES.flatMap((archetype) => SERVICE_FIELDS[archetype]).map((def) => [def.key, def]),
  ).values(),
);

type ServiceFormProps = {
  locale: string;
  mode: "create" | "edit";
  serviceId?: string;
  initialService?: ServiceSummary;
};

export function ServiceForm(props: ServiceFormProps) {
  const ts = useTranslations("services");
  if (props.mode === "edit" && (!props.serviceId || props.initialService?.id !== props.serviceId)) {
    return (
      <div className="flex min-h-[40vh] items-center justify-center">
        <Spinner label={ts("vendor.list.loading")} />
      </div>
    );
  }
  const identity = props.mode === "edit" ? (props.serviceId ?? props.initialService?.id) : "new";
  return <ServiceFormForIdentity key={`${props.mode}:${identity}`} {...props} />;
}

function ServiceFormForIdentity({ locale, mode, serviceId, initialService }: ServiceFormProps) {
  const ts = useTranslations("services");
  const tv = useTranslations("vendor");
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
    initialService?.from_price_ngwee ? ngweeToZmwInput(initialService.from_price_ngwee) : "",
  );
  const [portfolioImages, setPortfolioImages] = useState<string[]>(
    initialService?.portfolio_images ?? [],
  );
  const [bookable, setBookable] = useState(initialService?.bookable ?? false);
  const [isFree, setIsFree] = useState(initialService?.is_free ?? false);
  const [bookingPrice, setBookingPrice] = useState(
    initialService?.booking_price_ngwee ? ngweeToZmwInput(initialService.booking_price_ngwee) : "",
  );
  const [status, setStatus] = useState<ServiceStatus>(initialService?.status ?? "draft");
  const [archetypeOverride, setArchetypeOverride] = useState(
    initialService?.archetype_override ?? "",
  );
  const [attrValues, setAttrValues] = useState<FieldValues>(() =>
    valuesFromAttributes(ALL_SERVICE_DEFS, initialService?.attributes, ngweeToZmwInput),
  );
  const [attrErrors, setAttrErrors] = useState<AttributeErrors>({});
  const archetype = effectiveArchetype(archetypeOverride, category);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const active = useRef(true);
  const authGeneration = useRef(0);

  useLayoutEffect(() => {
    active.current = true;
    return () => {
      active.current = false;
    };
  }, []);
  useLayoutEffect(() => {
    authGeneration.current += 1;
  }, [session?.user.id]);

  const getToken = useCallback(() => session?.access_token ?? null, [session?.access_token]);
  const servicesClient = useMemo(() => createServicesClient(getToken), [getToken]);

  async function handleSave(nextStatus?: ServiceStatus) {
    const trimmedTitle = title.trim();
    if (Array.from(trimmedTitle).length < 2) {
      setError(ts("vendor.errors.titleInvalid"));
      return;
    }
    if (!isFree && fromPrice.trim() && !isValidZmwDecimal(fromPrice)) {
      setError(tv("listings.fields.priceInvalid"));
      return;
    }
    if (!isFree && bookable && !isValidZmwDecimal(bookingPrice)) {
      setError(ts("vendor.errors.bookablePrice"));
      return;
    }
    const attrs = attributesFromValues(SERVICE_FIELDS[archetype], attrValues);
    if (!attrs.ok) {
      setAttrErrors(attrs.errors);
      setError(ts("vendor.attributes.errors.fix"));
      return;
    }
    setAttrErrors({});
    const fromPriceNgwee = fromPrice.trim() ? zmwDecimalToNgwee(fromPrice) : null;
    const bookingPriceNgwee = isValidZmwDecimal(bookingPrice)
      ? zmwDecimalToNgwee(bookingPrice)
      : null;
    const submittingAuthGeneration = authGeneration.current;
    const isCurrentSave = () =>
      active.current && authGeneration.current === submittingAuthGeneration;

    setSaving(true);
    setError(null);

    const payload = {
      category,
      title: trimmedTitle,
      description: description.trim() || null,
      service_area: serviceArea.trim() || null,
      // A free service carries no price and is never bookable (paid deposit path).
      is_free: isFree,
      from_price_ngwee: isFree ? null : fromPriceNgwee,
      bookable: isFree ? false : bookable,
      booking_price_ngwee: isFree ? null : bookingPriceNgwee,
      status: nextStatus ?? status,
      // null = derived from the vertical; sent explicitly so a PATCH can clear an override.
      archetype: archetypeOverride || null,
      attributes: attrs.attributes,
      portfolio_images: portfolioImages,
      includes: includes
        .split("\n")
        .map((line) => line.trim())
        .filter((line) => line.length > 0),
    };

    try {
      if (mode === "create") {
        const created = await servicesClient.createService(payload);
        if (!isCurrentSave()) return;
        // Land on the edit page so the vendor can add packages straight away
        // (the packages editor only exists once the service has an id).
        const createdId = created?.service?.id;
        router.push(createdId ? `/${locale}/services/${createdId}/edit` : `/${locale}/services`);
        router.refresh();
        return;
      }
      if (!serviceId) {
        return;
      }
      await servicesClient.updateService(serviceId, payload);
      if (!isCurrentSave()) return;
      router.push(`/${locale}/services`);
      router.refresh();
    } catch (err) {
      if (!isCurrentSave()) return;
      if (err instanceof ApiError) {
        setError(err.message);
      } else {
        setError(ts("vendor.errors.saveFailed"));
      }
    } finally {
      if (active.current) setSaving(false);
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

      <div
        className="flex flex-col gap-1 rounded-md bg-bg-2 p-3 text-sm"
        data-testid="service-archetype-summary"
      >
        <p className="m-0 font-medium text-text">
          {ts("vendor.archetypes.summary", { type: ts(`vendor.archetypes.${archetype}.name`) })}
        </p>
        <p className="m-0 text-xs text-text-3">{ts(`vendor.archetypes.${archetype}.help`)}</p>
        <details>
          <summary className="min-h-11 cursor-pointer py-2 text-xs font-medium text-primary">
            {ts("vendor.archetypes.advanced")}
          </summary>
          <FormField id="archetype-override" label={ts("vendor.archetypes.overrideLabel")}>
            <Select
              id="archetype-override"
              value={archetypeOverride}
              onChange={(event) => setArchetypeOverride(event.target.value)}
            >
              <option value="">{ts("vendor.archetypes.derived")}</option>
              {ARCHETYPES.map((key) => (
                <option key={key} value={key}>
                  {ts(`vendor.archetypes.${key}.name`)}
                </option>
              ))}
            </Select>
          </FormField>
        </details>
      </div>

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

      <label className="flex items-start gap-2 text-sm text-text">
        <input
          type="checkbox"
          checked={isFree}
          onChange={(event) => setIsFree(event.target.checked)}
          className="mt-0.5 h-4 w-4"
        />
        <span>
          <span className="font-medium">{ts("vendor.form.isFreeLabel")}</span>
          <span className="block text-xs text-text-3">{ts("vendor.form.isFreeHint")}</span>
        </span>
      </label>

      {isFree ? null : (
        <>
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
        </>
      )}

      <p className="-mb-2 text-xs text-text-3" data-testid="service-photo-tip">
        {ts(`vendor.archetypes.${archetype}.photoTip`)}
      </p>
      <EventImagePicker
        images={portfolioImages}
        getToken={getToken}
        onChange={setPortfolioImages}
        disabled={saving}
        getAlt={(position) => ts("vendor.form.photoAlt", { position })}
      />

      <section className="flex flex-col gap-3" aria-labelledby="service-details-heading">
        <h2 id="service-details-heading" className="m-0 text-base font-semibold text-text">
          {ts("vendor.attributes.serviceHeading")}
        </h2>
        <AttributeFields
          scope="service"
          idPrefix="service"
          defs={SERVICE_FIELDS[archetype]}
          values={attrValues}
          errors={attrErrors}
          disabled={saving}
          onChange={setAttrValues}
        />
      </section>

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
