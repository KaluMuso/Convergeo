"use client";

import { useSession } from "@vergeo/auth/use-session";
import { notify } from "@vergeo/ui/src/toast";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useTranslations } from "next-intl";
import { useCallback, useEffect, useMemo, useState } from "react";

import { VendorErrorState } from "../../../../_components/async-state";
import { VendorFormLayout } from "../../../../_components/vendor-page";
import { ListSkeleton } from "../../../../_components/vendor-skeletons";
import { vendorErrorMessageKey } from "../../../../_lib/vendor-errors";
import { ImageManager, type ListingImageRecord } from "../../../_components/image-manager";
import { ListingFormAside } from "../../../_components/listing-form-aside";
import { ListingVisibilityHint } from "../../../_components/listing-guide";
import { ListingProductStatusChip } from "../../../_components/listing-product-status";
import { VariantsEditor } from "../../../_components/variants-editor";
import {
  ListingFields,
  listingFieldErrors,
  parseListingFieldValues,
  requiresListingEvidence,
  type ListingFieldValues,
} from "../../../new/_components/listing-fields";
import {
  buildListingFieldLabels,
  FIELD_ERRORS_KEY,
  readFieldErrorMessages,
} from "../../../new/_lib/field-labels";
import { describeListingError } from "../../../new/_lib/listing-errors";
import { milliToUnitInput } from "../../../new/_lib/measure";
import { FULFILMENT_OPTIONS, USED_GRADES } from "../../../new/_lib/types";
import { Badge, Button, FormField, Input, Switch } from "../../../new/_lib/ui";
import { createManageClient, type ListingSummary, type PriceTier } from "../_lib/manage-client";
import { isValidZmwDecimal, ngweeToZmwInput, zmwDecimalToNgwee } from "../_lib/money";

import { StockEditor } from "./stock-editor";

type ListingEditFormProps = {
  locale: string;
  listingId: string;
};

type TierDraft = {
  minQty: string;
  priceZmw: string;
};

function tiersFromListing(listing: ListingSummary): TierDraft[] {
  if (!listing.price_tiers?.length) {
    return [];
  }
  return listing.price_tiers.map((tier) => ({
    minQty: String(tier.min_qty),
    priceZmw: ngweeToZmwInput(tier.price_ngwee),
  }));
}

export function ListingEditForm({ locale, listingId }: ListingEditFormProps) {
  const t = useTranslations("vendor");
  const tCommon = useTranslations("common");
  const router = useRouter();
  const { session, loading: sessionLoading } = useSession();
  const [listing, setListing] = useState<ListingSummary | null>(null);
  const [fieldValues, setFieldValues] = useState<ListingFieldValues | null>(null);
  const [returnable, setReturnable] = useState(false);
  const [returnWindowHours, setReturnWindowHours] = useState("");
  const [compareAtZmw, setCompareAtZmw] = useState("");
  const [tiers, setTiers] = useState<TierDraft[]>([]);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [actionLoading, setActionLoading] = useState<
    "publish" | "pause" | "unpause" | "delete" | null
  >(null);
  const [error, setError] = useState<string | null>(null);
  const [loadErrorKey, setLoadErrorKey] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [fieldErrors, setFieldErrors] = useState<Record<string, string>>({});
  const [reloadKey, setReloadKey] = useState(0);

  const getToken = useCallback(() => session?.access_token ?? null, [session?.access_token]);
  const manageClient = useMemo(() => createManageClient(getToken), [getToken]);

  const fieldLabels = useMemo(
    () => buildListingFieldLabels(t as unknown as (key: string) => string),
    [t],
  );

  const fieldErrorMessages = useMemo(() => readFieldErrorMessages(t.raw(FIELD_ERRORS_KEY)), [t]);

  useEffect(() => {
    if (sessionLoading) {
      return;
    }
    if (!session) {
      setLoading(false);
      return;
    }

    let cancelled = false;
    setLoading(true);
    setLoadErrorKey(null);
    manageClient
      .getListing(listingId)
      .then((row) => {
        if (cancelled) {
          return;
        }
        setListing(row);
        setFieldValues({
          priceZmw: ngweeToZmwInput(row.price_ngwee),
          productClass: row.product_class ?? "A",
          saleUnit: row.sale_unit ?? "each",
          unitStep: milliToUnitInput(row.unit_step_milli ?? 1_000),
          minSteps: String(row.min_steps ?? 1),
          condition: row.condition,
          conditionDetail: (USED_GRADES as readonly string[]).includes(row.condition_detail ?? "")
            ? (row.condition_detail as (typeof USED_GRADES)[number])
            : "used_good",
          defectNotes: row.defect_notes ?? "",
          fulfilmentOptions:
            row.fulfilment_options && row.fulfilment_options.length > 0
              ? FULFILMENT_OPTIONS.filter((option) => row.fulfilment_options?.includes(option))
              : ["lusaka_delivery", "pickup_shop"],
          fulfilmentMode: row.fulfilment_mode ?? "stocked",
          leadTimeDays: row.lead_time_days === null ? "" : String(row.lead_time_days ?? ""),
          vendorCapacityPerWeek:
            row.vendor_capacity_per_week === null ? "" : String(row.vendor_capacity_per_week ?? ""),
          stockMode: row.stock_mode,
          stockQty: row.stock_qty === null ? "" : String(row.stock_qty),
          wholesale: row.wholesale,
          moq: String(row.moq),
        });
        setReturnable(row.returnable);
        setReturnWindowHours(
          row.return_window_hours === null ? "" : String(row.return_window_hours),
        );
        setCompareAtZmw(row.compare_at_ngwee === null ? "" : ngweeToZmwInput(row.compare_at_ngwee));
        setTiers(tiersFromListing(row));
        setError(null);
      })
      .catch((caught: unknown) => {
        if (!cancelled) {
          setListing(null);
          setFieldValues(null);
          setLoadErrorKey(vendorErrorMessageKey(caught, "listingsManage"));
        }
      })
      .finally(() => {
        if (!cancelled) {
          setLoading(false);
        }
      });

    return () => {
      cancelled = true;
    };
  }, [listingId, manageClient, reloadKey, session, sessionLoading]);

  const buildPriceTiers = (): PriceTier[] | null => {
    if (!fieldValues?.wholesale) {
      return null;
    }
    if (
      tiers.length === 0 ||
      tiers.some(
        (tier) =>
          !/^[1-9]\d*$/.test(tier.minQty.trim()) ||
          !Number.isSafeInteger(Number(tier.minQty)) ||
          !isValidZmwDecimal(tier.priceZmw),
      )
    ) {
      return null;
    }
    const parsed = tiers
      .map((tier) => ({
        min_qty: Number(tier.minQty),
        price_ngwee: zmwDecimalToNgwee(tier.priceZmw),
      }))
      .sort((a, b) => a.min_qty - b.min_qty);
    if (
      parsed.some((tier, index) => {
        const previous = parsed[index - 1];
        return (
          previous !== undefined &&
          (tier.min_qty <= previous.min_qty || tier.price_ngwee >= previous.price_ngwee)
        );
      })
    ) {
      return null;
    }
    return parsed;
  };

  const handleSave = async () => {
    if (!fieldValues) {
      return;
    }
    const clientErrors = listingFieldErrors(fieldValues, fieldLabels);
    if (Object.keys(clientErrors).length > 0) {
      setFieldErrors(clientErrors);
      setError(t("listings.errors.draftInvalid"));
      return;
    }
    setFieldErrors({});
    const priceTiers = buildPriceTiers();
    if (fieldValues.wholesale && priceTiers === null) {
      setError(t("listings.errors.invalid_tiers"));
      return;
    }
    if (
      listing?.status === "active" &&
      requiresListingEvidence(fieldValues) &&
      (listing.images?.length ?? 0) === 0
    ) {
      setError(t("listings.manage.edit.evidenceRequired"));
      return;
    }
    if (returnable && !returnWindowHours) {
      setError(t("listings.manage.errors.returnWindowRequired"));
      return;
    }
    const trimmedCompareAt = compareAtZmw.trim();
    if (trimmedCompareAt !== "" && !isValidZmwDecimal(trimmedCompareAt)) {
      setError(t("listings.manage.edit.compareAtInvalid"));
      return;
    }

    setSaving(true);
    setError(null);
    setNotice(null);
    try {
      const parsed = parseListingFieldValues(fieldValues);
      const compareAtNgwee = trimmedCompareAt === "" ? null : zmwDecimalToNgwee(trimmedCompareAt);
      if (compareAtNgwee !== null && compareAtNgwee <= parsed.priceNgwee) {
        setError(t("listings.manage.edit.compareAtTooLow"));
        return;
      }
      const response = await manageClient.updateListing(listingId, {
        price_ngwee: parsed.priceNgwee,
        compare_at_ngwee: compareAtNgwee,
        product_class: fieldValues.productClass,
        sale_unit: fieldValues.saleUnit,
        unit_step_milli: parsed.unitStepMilli,
        min_steps: parsed.minSteps,
        condition: fieldValues.condition,
        defect_notes: parsed.defectNotes,
        condition_detail: parsed.conditionDetail,
        fulfilment_options: fieldValues.fulfilmentOptions,
        fulfilment_mode: fieldValues.fulfilmentMode,
        lead_time_days: parsed.leadTimeDays,
        vendor_capacity_per_week: parsed.vendorCapacityPerWeek,
        wholesale: fieldValues.wholesale,
        moq: parsed.moq,
        price_tiers: priceTiers,
        returnable,
        return_window_hours: returnable ? Number(returnWindowHours) : null,
      });
      setListing((current) => ({
        ...response.listing,
        images: response.listing.images ?? current?.images,
      }));
      // The available quantity may have changed while a price edit was open.
      // Keep the next save from reintroducing the old stock value.
      setFieldValues((current) =>
        current
          ? {
              ...current,
              stockMode: response.listing.stock_mode,
              stockQty:
                response.listing.stock_qty === null ? "" : String(response.listing.stock_qty),
            }
          : current,
      );
      setTiers(tiersFromListing(response.listing));
      const savedNotice = response.cart_revalidation?.has_changes
        ? t("listings.manage.edit.priceChangedNotice")
        : t("listings.manage.edit.saved");
      setNotice(savedNotice);
      notify.success(savedNotice);
    } catch (caught: unknown) {
      const result = describeListingError(
        caught,
        {
          standaloneRequired: t("listings.errors.standalone_required"),
          draftInvalid: t("listings.errors.draftInvalid"),
          publishBlocked: t("listings.errors.publishBlocked"),
          fieldErrors: fieldErrorMessages,
          fallback: t("listings.manage.errors.saveFailed"),
        },
        listing?.status === "active" ? "publish" : "draft",
      );
      setFieldErrors(result.fields);
      const summary = [result.message, ...result.unplaced].join(" ");
      setError(summary);
      notify.error(summary);
    } finally {
      setSaving(false);
    }
  };

  const handlePauseToggle = async () => {
    if (!listing) {
      return;
    }
    setActionLoading(
      listing.status === "draft" ? "publish" : listing.status === "paused" ? "unpause" : "pause",
    );
    setError(null);
    try {
      const response =
        listing.status === "draft"
          ? await manageClient.updateListing(listingId, { status: "active" })
          : listing.status === "paused"
            ? await manageClient.unpauseListing(listingId)
            : await manageClient.pauseListing(listingId);
      setListing((current) => ({
        ...response.listing,
        images: response.listing.images ?? current?.images,
      }));
      setNotice(t("listings.manage.edit.saved"));
      notify.success(t("listings.manage.edit.saved"));
    } catch (caught: unknown) {
      const result = describeListingError(
        caught,
        {
          standaloneRequired: t("listings.errors.standalone_required"),
          draftInvalid: t("listings.errors.draftInvalid"),
          publishBlocked: t("listings.errors.publishBlocked"),
          fieldErrors: fieldErrorMessages,
          fallback: t("listings.manage.errors.saveFailed"),
        },
        listing.status === "draft" ? "publish" : "draft",
      );
      setFieldErrors(result.fields);
      const summary = [result.message, ...result.unplaced].join(" ");
      setError(summary);
      notify.error(summary);
    } finally {
      setActionLoading(null);
    }
  };

  const handleDelete = async () => {
    setActionLoading("delete");
    setError(null);
    setNotice(null);
    try {
      const response = await manageClient.deleteListing(listingId);
      if (response.paused_instead) {
        setNotice(t("listings.manage.delete.paused_instead"));
        setListing((current) => (current ? { ...current, status: response.status } : current));
      } else {
        setNotice(t("listings.manage.delete.removed"));
        router.push(`/${locale}/listings`);
      }
    } catch {
      setError(t("listings.manage.errors.saveFailed"));
      notify.error(t("listings.manage.errors.saveFailed"));
    } finally {
      setActionLoading(null);
    }
  };

  if (sessionLoading || loading) {
    return <ListSkeleton label={t("listings.manage.loading")} rows={4} />;
  }

  if (!session) {
    return (
      <VendorErrorState
        title={t("listings.errors.authRequired")}
        retryLabel={tCommon("common.retry")}
      />
    );
  }

  if (loadErrorKey || !listing || !fieldValues) {
    return (
      <VendorErrorState
        title={t(
          (loadErrorKey ??
            "listings.manage.errors.loadFailed") as "listings.manage.errors.loadFailed",
        )}
        body={t("listings.errors.retryHint")}
        retryLabel={tCommon("common.retry")}
        onRetry={() => setReloadKey((value) => value + 1)}
      />
    );
  }

  if (listing.status === "removed") {
    return (
      <div className="flex flex-col gap-3" data-testid="listing-removed-state">
        <h1 className="text-xl font-semibold text-text">{t("listings.manage.removed.title")}</h1>
        <p className="text-sm text-text-2">{listing.title}</p>
        <p className="text-sm text-text-2" role="status">
          {t("listings.manage.removed.body")}
        </p>
        <Link
          href={`/${locale}/listings`}
          className="inline-flex min-h-11 w-full items-center justify-center rounded-md border border-border px-4 text-sm font-medium text-text"
        >
          {t("listings.manage.removed.back")}
        </Link>
      </div>
    );
  }

  const statusLabel =
    listing.status === "active"
      ? t("listings.manage.status.active")
      : listing.status === "paused"
        ? t("listings.manage.status.paused")
        : t("listings.manage.status.draft");
  const evidenceRequired = requiresListingEvidence(fieldValues);
  const persistedEvidenceRequired = listing.condition === "used";
  const hasEvidence = (listing.images?.length ?? 0) > 0;
  const minimumEvidenceImages =
    listing.status === "active" && (persistedEvidenceRequired || evidenceRequired) ? 1 : 0;
  const activationBlocked = listing.status !== "active" && evidenceRequired && !hasEvidence;

  return (
    <div className="flex flex-col gap-4">
      <header className="space-y-1">
        <h1 className="text-xl font-semibold text-text">{t("listings.manage.edit.title")}</h1>
        <p className="text-sm text-text-2">{listing.title}</p>
        <div className="flex items-center gap-2 pt-1">
          <span className="text-xs text-text-2">{t("listings.manage.statusLabel")}</span>
          <Badge
            variant={
              listing.status === "active"
                ? "free"
                : listing.status === "paused"
                  ? "sold_out"
                  : "new"
            }
            label={statusLabel}
          />
        </div>
        <ListingVisibilityHint status={listing.status} />
        <ListingProductStatusChip
          listingStatus={listing.status}
          productStatus={listing.product_status}
        />
      </header>

      <VendorFormLayout
        aside={
          <ListingFormAside
            title={listing.title}
            priceNgwee={listing.price_ngwee}
            listingStatus={listing.status}
            productStatus={listing.product_status}
            coverPublicId={
              [...(listing.images ?? [])].sort((a, b) => a.position - b.position)[0]
                ?.cloudinary_public_id
            }
          />
        }
        main={
          <>
            {error ? (
              <p className="text-sm text-danger" role="alert">
                {error}
              </p>
            ) : null}
            {notice ? (
              <p className="text-sm text-success" role="status">
                {notice}
              </p>
            ) : null}

            <ListingFields
              inventoryReadOnly
              values={fieldValues}
              onChange={(patch) =>
                setFieldValues((current) => (current ? { ...current, ...patch } : current))
              }
              wholesaleEnabled={fieldValues.wholesale}
              labels={fieldLabels}
              errors={fieldErrors}
              allowStandaloneClasses={listing.product_id === null}
            />

            <StockEditor
              listingId={listingId}
              client={manageClient}
              ownerId={session?.user.id ?? ""}
            />

            <FormField
              label={t("listings.manage.edit.compareAtLabel")}
              helpText={t("listings.manage.edit.compareAtHelp")}
            >
              <Input
                inputMode="decimal"
                placeholder={fieldLabels.pricePlaceholder}
                value={compareAtZmw}
                onChange={(event) => setCompareAtZmw(event.target.value)}
              />
            </FormField>

            <div className="space-y-3 rounded-lg border border-border p-3">
              <div className="flex items-center justify-between gap-3">
                <div>
                  <p className="text-sm font-medium text-text">
                    {t("listings.manage.edit.returnableLabel")}
                  </p>
                  <p className="text-xs text-text-2">{t("listings.manage.edit.returnableHelp")}</p>
                </div>
                <Switch
                  label={t("listings.manage.edit.returnableLabel")}
                  checked={returnable}
                  onChange={(event) => setReturnable(event.target.checked)}
                />
              </div>
              {returnable ? (
                <FormField label={t("listings.manage.edit.returnWindowLabel")}>
                  <Input
                    inputMode="numeric"
                    value={returnWindowHours}
                    onChange={(event) => setReturnWindowHours(event.target.value)}
                  />
                </FormField>
              ) : null}
            </div>

            <ImageManager
              listingId={listingId}
              images={(listing.images ?? []) as ListingImageRecord[]}
              getToken={getToken}
              minimumImages={minimumEvidenceImages}
              onImagesChange={(images) =>
                setListing((current) => (current ? { ...current, images } : current))
              }
            />

            <VariantsEditor
              listingId={listingId}
              client={manageClient}
              imagePublicIds={[...(listing.images ?? [])]
                .sort((a, b) => a.position - b.position)
                .map((image) => image.cloudinary_public_id)}
              stockTracked={listing.stock_mode === "tracked"}
              listingPriceNgwee={listing.price_ngwee}
              unsupportedReason={
                listing.product_class === "E"
                  ? "classE"
                  : listing.wholesale || (listing.price_tiers?.length ?? 0) > 0
                    ? "wholesale"
                    : (listing.sale_unit ?? "each") !== "each"
                      ? "measured"
                      : null
              }
            />

            {activationBlocked ? (
              <p
                className="rounded-lg border border-warning/30 bg-warning/10 p-3 text-sm text-text"
                role="status"
              >
                {t("listings.manage.edit.evidenceRequired")}
              </p>
            ) : null}

            {fieldValues.wholesale ? (
              <section
                id="wholesale"
                className="space-y-3 rounded-lg border border-border p-3"
                aria-labelledby="listing-edit-wholesale-heading"
              >
                <h3
                  id="listing-edit-wholesale-heading"
                  className="font-display text-h4 text-display-ink"
                >
                  {t("listings.fields.wholesaleSectionHeading")}
                </h3>
                <p className="text-xs text-text-2">{t("listings.fields.wholesaleBuyersHint")}</p>
                <p className="text-sm font-medium text-text">
                  {t("listings.manage.edit.tierHeading")}
                </p>
                {tiers.map((tier, index) => (
                  <div key={`tier-${index}`} className="grid grid-cols-[1fr_1fr_auto] gap-2">
                    <FormField label={t("listings.manage.edit.tierQtyLabel")}>
                      <Input
                        inputMode="numeric"
                        value={tier.minQty}
                        onChange={(event) =>
                          setTiers((current) =>
                            current.map((row, rowIndex) =>
                              rowIndex === index ? { ...row, minQty: event.target.value } : row,
                            ),
                          )
                        }
                      />
                    </FormField>
                    <FormField label={t("listings.manage.edit.tierPriceLabel")}>
                      <Input
                        inputMode="decimal"
                        value={tier.priceZmw}
                        onChange={(event) =>
                          setTiers((current) =>
                            current.map((row, rowIndex) =>
                              rowIndex === index ? { ...row, priceZmw: event.target.value } : row,
                            ),
                          )
                        }
                      />
                    </FormField>
                    <Button
                      type="button"
                      variant="secondary"
                      className="mt-6 min-h-11"
                      loadingLabel={t("listings.manage.edit.saving")}
                      onClick={() =>
                        setTiers((current) => current.filter((_, rowIndex) => rowIndex !== index))
                      }
                    >
                      {t("listings.manage.edit.removeTier")}
                    </Button>
                  </div>
                ))}
                <Button
                  type="button"
                  variant="secondary"
                  className="min-h-11 w-full"
                  loadingLabel={t("listings.manage.edit.saving")}
                  onClick={() => setTiers((current) => [...current, { minQty: "", priceZmw: "" }])}
                >
                  {t("listings.manage.edit.addTier")}
                </Button>
              </section>
            ) : null}

            <Button
              type="button"
              className="min-h-11 w-full"
              disabled={saving}
              loading={saving}
              loadingLabel={t("listings.manage.edit.saving")}
              onClick={() => void handleSave()}
            >
              {saving ? t("listings.manage.edit.saving") : t("listings.manage.edit.save")}
            </Button>

            <Button
              type="button"
              variant="secondary"
              className="min-h-11 w-full"
              disabled={actionLoading !== null || activationBlocked}
              loading={
                actionLoading === "publish" ||
                actionLoading === "pause" ||
                actionLoading === "unpause"
              }
              loadingLabel={
                actionLoading === "publish"
                  ? t("listings.manage.edit.publishingListing")
                  : actionLoading === "pause"
                    ? t("listings.manage.edit.pausing")
                    : t("listings.manage.edit.unpausing")
              }
              onClick={() => void handlePauseToggle()}
            >
              {actionLoading === "publish"
                ? t("listings.manage.edit.publishingListing")
                : actionLoading === "pause"
                  ? t("listings.manage.edit.pausing")
                  : actionLoading === "unpause"
                    ? t("listings.manage.edit.unpausing")
                    : listing.status === "draft"
                      ? t("listings.manage.edit.publishListing")
                      : listing.status === "paused"
                        ? t("listings.manage.edit.unpause")
                        : t("listings.manage.edit.pause")}
            </Button>

            <Button
              type="button"
              variant="secondary"
              className="min-h-11 w-full text-danger"
              disabled={actionLoading !== null}
              loading={actionLoading === "delete"}
              loadingLabel={t("listings.manage.edit.deleting")}
              onClick={() => void handleDelete()}
            >
              {actionLoading === "delete"
                ? t("listings.manage.edit.deleting")
                : t("listings.manage.edit.delete")}
            </Button>
          </>
        }
      />
    </div>
  );
}
