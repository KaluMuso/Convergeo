"use client";

import { useSession } from "@vergeo/auth/use-session";
import { useRouter } from "next/navigation";
import { useTranslations } from "next-intl";
import { useCallback, useEffect, useMemo, useState } from "react";

import {
  parseListingFieldValues,
  validateListingFields,
  type ListingFieldValues,
} from "../../../new/_components/listing-fields";
import { Button, FormField, Input, Select, Spinner, Switch } from "../../../new/_lib/ui";
import { createManageClient, type ListingSummary, type PriceTier } from "../_lib/manage-client";
import { isValidZmwDecimal, ngweeToZmwInput, zmwDecimalToNgwee } from "../_lib/money";

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
  const router = useRouter();
  const { session, loading: sessionLoading } = useSession();
  const [listing, setListing] = useState<ListingSummary | null>(null);
  const [fieldValues, setFieldValues] = useState<ListingFieldValues | null>(null);
  const [returnable, setReturnable] = useState(false);
  const [returnWindowHours, setReturnWindowHours] = useState("");
  const [tiers, setTiers] = useState<TierDraft[]>([]);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [actionLoading, setActionLoading] = useState<"pause" | "unpause" | "delete" | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  const getToken = useCallback(() => session?.access_token ?? null, [session?.access_token]);
  const manageClient = useMemo(() => createManageClient(getToken), [getToken]);

  const fieldLabels = useMemo(
    () => ({
      priceLabel: t("listings.fields.priceLabel"),
      pricePlaceholder: t("listings.fields.pricePlaceholder"),
      priceHelp: t("listings.fields.priceHelp"),
      priceInvalid: t("listings.fields.priceInvalid"),
      conditionLabel: t("listings.fields.conditionLabel"),
      conditionNew: t("listings.fields.conditionNew"),
      conditionRefurbished: t("listings.fields.conditionRefurbished"),
      stockModeLabel: t("listings.fields.stockModeLabel"),
      stockTracked: t("listings.fields.stockTracked"),
      stockAlways: t("listings.fields.stockAlways"),
      stockQtyLabel: t("listings.fields.stockQtyLabel"),
      wholesaleLabel: t("listings.fields.wholesaleLabel"),
      wholesaleHelp: t("listings.fields.wholesaleHelp"),
      moqLabel: t("listings.fields.moqLabel"),
      required: t("listings.errors.required"),
    }),
    [t],
  );

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
    manageClient
      .getListing(listingId)
      .then((row) => {
        if (cancelled) {
          return;
        }
        setListing(row);
        setFieldValues({
          priceZmw: ngweeToZmwInput(row.price_ngwee),
          condition: row.condition,
          stockMode: row.stock_mode,
          stockQty: row.stock_qty === null ? "" : String(row.stock_qty),
          wholesale: row.wholesale,
          moq: String(row.moq),
        });
        setReturnable(row.returnable);
        setReturnWindowHours(
          row.return_window_hours === null ? "" : String(row.return_window_hours),
        );
        setTiers(tiersFromListing(row));
        setError(null);
      })
      .catch(() => {
        if (!cancelled) {
          setError(t("listings.manage.errors.loadFailed"));
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
  }, [listingId, manageClient, session, sessionLoading, t]);

  const buildPriceTiers = (): PriceTier[] | undefined => {
    if (!fieldValues?.wholesale) {
      return undefined;
    }
    return tiers
      .filter((tier) => tier.minQty && isValidZmwDecimal(tier.priceZmw))
      .map((tier) => ({
        min_qty: Number(tier.minQty),
        price_ngwee: zmwDecimalToNgwee(tier.priceZmw),
      }));
  };

  const handleSave = async () => {
    if (!fieldValues) {
      return;
    }
    const validationError = validateListingFields(fieldValues, fieldLabels);
    if (validationError) {
      setError(validationError);
      return;
    }
    if (returnable && !returnWindowHours) {
      setError(t("listings.manage.errors.returnWindowRequired"));
      return;
    }

    setSaving(true);
    setError(null);
    setNotice(null);
    try {
      const parsed = parseListingFieldValues(fieldValues);
      const response = await manageClient.updateListing(listingId, {
        price_ngwee: parsed.priceNgwee,
        condition: fieldValues.condition,
        stock_mode: fieldValues.stockMode,
        stock_qty: parsed.stockQty,
        wholesale: fieldValues.wholesale,
        moq: parsed.moq,
        price_tiers: buildPriceTiers(),
        returnable,
        return_window_hours: returnable ? Number(returnWindowHours) : null,
      });
      setListing(response.listing);
      setNotice(
        response.cart_revalidation?.has_changes
          ? t("listings.manage.edit.priceChangedNotice")
          : t("listings.manage.edit.saved"),
      );
    } catch {
      setError(t("listings.manage.errors.saveFailed"));
    } finally {
      setSaving(false);
    }
  };

  const handlePauseToggle = async () => {
    if (!listing) {
      return;
    }
    setActionLoading(listing.status === "paused" ? "unpause" : "pause");
    setError(null);
    try {
      const response =
        listing.status === "paused"
          ? await manageClient.unpauseListing(listingId)
          : await manageClient.pauseListing(listingId);
      setListing(response.listing);
      setNotice(t("listings.manage.edit.saved"));
    } catch {
      setError(t("listings.manage.errors.saveFailed"));
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
    } finally {
      setActionLoading(null);
    }
  };

  if (sessionLoading || loading || !fieldValues) {
    return (
      <div className="flex min-h-40 items-center justify-center">
        <Spinner label={t("listings.manage.loading")} />
      </div>
    );
  }

  if (!listing) {
    return <p className="text-sm text-danger">{error ?? t("listings.manage.errors.loadFailed")}</p>;
  }

  return (
    <div className="flex flex-col gap-4">
      <header className="space-y-1">
        <h1 className="text-xl font-semibold text-text">{t("listings.manage.edit.title")}</h1>
        <p className="text-sm text-text-2">{listing.title}</p>
      </header>

      {error ? <p className="text-sm text-danger">{error}</p> : null}
      {notice ? <p className="text-sm text-success">{notice}</p> : null}

      <FormField label={fieldLabels.priceLabel} helpText={fieldLabels.priceHelp}>
        <Input
          inputMode="decimal"
          placeholder={fieldLabels.pricePlaceholder}
          value={fieldValues.priceZmw}
          onChange={(event) =>
            setFieldValues((current) =>
              current ? { ...current, priceZmw: event.target.value } : current,
            )
          }
        />
      </FormField>

      <FormField label={fieldLabels.conditionLabel}>
        <Select
          value={fieldValues.condition}
          onChange={(event) =>
            setFieldValues((current) =>
              current
                ? { ...current, condition: event.target.value as ListingFieldValues["condition"] }
                : current,
            )
          }
        >
          <option value="new">{fieldLabels.conditionNew}</option>
          <option value="refurbished">{fieldLabels.conditionRefurbished}</option>
        </Select>
      </FormField>

      <FormField label={fieldLabels.stockModeLabel}>
        <Select
          value={fieldValues.stockMode}
          onChange={(event) =>
            setFieldValues((current) =>
              current
                ? { ...current, stockMode: event.target.value as ListingFieldValues["stockMode"] }
                : current,
            )
          }
        >
          <option value="tracked">{fieldLabels.stockTracked}</option>
          <option value="always_available">{fieldLabels.stockAlways}</option>
        </Select>
      </FormField>

      {fieldValues.stockMode === "tracked" ? (
        <FormField label={fieldLabels.stockQtyLabel}>
          <Input
            inputMode="numeric"
            value={fieldValues.stockQty}
            onChange={(event) =>
              setFieldValues((current) =>
                current ? { ...current, stockQty: event.target.value } : current,
              )
            }
          />
        </FormField>
      ) : null}

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

      {fieldValues.wholesale ? (
        <div className="space-y-3 rounded-lg border border-border p-3">
          <p className="text-sm font-medium text-text">{t("listings.manage.edit.tierHeading")}</p>
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
        </div>
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
        disabled={actionLoading !== null}
        loading={actionLoading === "pause" || actionLoading === "unpause"}
        loadingLabel={
          actionLoading === "pause"
            ? t("listings.manage.edit.pausing")
            : t("listings.manage.edit.unpausing")
        }
        onClick={() => void handlePauseToggle()}
      >
        {actionLoading === "pause"
          ? t("listings.manage.edit.pausing")
          : actionLoading === "unpause"
            ? t("listings.manage.edit.unpausing")
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
    </div>
  );
}
