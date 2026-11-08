"use client";

import { ApiError } from "@vergeo/config";
import { useTranslations } from "next-intl";
import { useCallback, useEffect, useMemo, useState } from "react";

import { ngweeToZmwInput } from "../[id]/edit/_lib/money";
import {
  MAX_GROUPS,
  generateMatrix,
  newKey,
  toPayload,
  validateDraft,
  type GroupDraft,
  type VariantErrorKey,
  type VariantErrors,
  type VariantRowDraft,
} from "../_lib/variant-matrix";
import { Button, FormField, Input, Spinner, Switch } from "../new/_lib/ui";

import type { ListingVariantsResponse } from "../[id]/edit/_lib/manage-client";

type VariantsClient = {
  getVariants(listingId: string): Promise<ListingVariantsResponse>;
  replaceVariants(
    listingId: string,
    payload: ReturnType<typeof toPayload>,
  ): Promise<ListingVariantsResponse>;
};

export type VariantsEditorProps = {
  listingId: string;
  client: VariantsClient;
  /** Listing photos the vendor can assign to a variant (public ids, in order). */
  imagePublicIds: string[];
  stockTracked: boolean;
  listingPriceNgwee: number;
  /** Class E, wholesale and measured listings cannot have variants. */
  unsupportedReason?: "classE" | "wholesale" | "measured" | null;
};

function fromResponse(response: ListingVariantsResponse): {
  groups: GroupDraft[];
  rows: VariantRowDraft[];
} {
  const groups: GroupDraft[] = response.groups.map((group) => ({
    key: newKey("group"),
    name: group.name,
    display: group.display === "swatch" ? "swatch" : "pill",
    values: group.values.map((value) => ({
      key: newKey("value"),
      label: value.label,
      swatchHex: value.swatch_hex ?? "",
    })),
  }));
  const rows: VariantRowDraft[] = response.variants
    .filter((variant) => variant.options.length === groups.length)
    .map((variant) => ({
      options: variant.options,
      sku: variant.sku ?? "",
      stock: variant.stock_qty === null ? "" : String(variant.stock_qty),
      price: variant.price_ngwee === null ? "" : ngweeToZmwInput(variant.price_ngwee),
      imagePublicId: variant.image_public_id ?? "",
      active: variant.status === "active",
    }));
  return { groups, rows: generateMatrix(groups, rows) };
}

export function VariantsEditor({
  listingId,
  client,
  imagePublicIds,
  stockTracked,
  listingPriceNgwee,
  unsupportedReason = null,
}: VariantsEditorProps) {
  const t = useTranslations("vendor");
  const [loading, setLoading] = useState(true);
  const [groups, setGroups] = useState<GroupDraft[]>([]);
  const [rows, setRows] = useState<VariantRowDraft[]>([]);
  const [errors, setErrors] = useState<VariantErrors>({});
  const [saving, setSaving] = useState(false);
  const [status, setStatus] = useState<{ kind: "saved" | "error"; message: string } | null>(null);
  const [loadFailed, setLoadFailed] = useState(false);

  useEffect(() => {
    let cancelled = false;
    client
      .getVariants(listingId)
      .then((response) => {
        if (cancelled) {
          return;
        }
        const draft = fromResponse(response);
        setGroups(draft.groups);
        setRows(draft.rows);
      })
      .catch(() => {
        if (!cancelled) {
          setLoadFailed(true);
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
    // Load once per listing; never re-fetch (and wipe the vendor's draft) on re-render.
  }, [client, listingId]);

  const errorText = useCallback(
    (key: VariantErrorKey | undefined) =>
      key ? t(`listings.variants.errors.${key}`, { max: MAX_GROUPS }) : undefined,
    [t],
  );

  const updateGroups = useCallback((next: GroupDraft[]) => {
    setGroups(next);
    setRows((current) => generateMatrix(next, current));
    setErrors({});
    setStatus(null);
  }, []);

  const updateRow = useCallback((index: number, patch: Partial<VariantRowDraft>) => {
    setRows((current) => current.map((row, i) => (i === index ? { ...row, ...patch } : row)));
    setStatus(null);
  }, []);

  const listingPriceInput = useMemo(() => ngweeToZmwInput(listingPriceNgwee), [listingPriceNgwee]);

  const save = useCallback(async () => {
    const found = validateDraft(groups, rows, { stockTracked });
    setErrors(found);
    if (Object.keys(found).length > 0) {
      setStatus({ kind: "error", message: t("listings.variants.fixErrors") });
      return;
    }
    setSaving(true);
    setStatus(null);
    try {
      const response = await client.replaceVariants(listingId, toPayload(groups, rows));
      const draft = fromResponse(response);
      setGroups(draft.groups);
      setRows(draft.rows);
      setStatus({ kind: "saved", message: t("listings.variants.saved") });
    } catch (error) {
      const reason =
        error instanceof ApiError && typeof error.details.reason === "string"
          ? (error.details.reason as VariantErrorKey)
          : null;
      setStatus({
        kind: "error",
        message: reason
          ? t(`listings.variants.errors.${reason}`, { max: MAX_GROUPS })
          : t("listings.variants.saveFailed"),
      });
    } finally {
      setSaving(false);
    }
  }, [client, groups, listingId, rows, stockTracked, t]);

  if (unsupportedReason) {
    return (
      <section className="flex flex-col gap-2" data-testid="variants-editor">
        <h2 className="font-display text-h4 text-display-ink">{t("listings.variants.heading")}</h2>
        <p className="text-sm text-text-2" role="note">
          {t(`listings.variants.unsupported.${unsupportedReason}`)}
        </p>
      </section>
    );
  }

  if (loading) {
    return <Spinner label={t("listings.variants.loading")} />;
  }

  return (
    <section
      id="options"
      className="flex flex-col gap-4 rounded-lg border border-border p-3"
      data-testid="variants-editor"
      aria-labelledby="variants-heading"
    >
      <header className="space-y-1">
        <h2 id="variants-heading" className="font-display text-h4 text-display-ink">
          {t("listings.variants.heading")}
        </h2>
        <p className="text-sm text-text-2">{t("listings.variants.intro")}</p>
      </header>

      {groups.map((group, gi) => (
        <fieldset
          key={group.key}
          className="flex flex-col gap-3 rounded-lg border border-border p-3"
          data-testid={`variants-group-${gi}`}
        >
          <legend className="px-1 text-sm font-medium text-text">
            {t("listings.variants.groupLegend", { number: gi + 1 })}
          </legend>
          <FormField
            label={t("listings.variants.groupName")}
            helpText={t("listings.variants.groupNameHint")}
            errorMessage={errorText(errors[`groups.${gi}.name`])}
          >
            <Input
              value={group.name}
              data-testid={`variants-group-name-${gi}`}
              onChange={(event) =>
                updateGroups(
                  groups.map((g, i) => (i === gi ? { ...g, name: event.target.value } : g)),
                )
              }
            />
          </FormField>
          <Switch
            label={t("listings.variants.showAsSwatches")}
            checked={group.display === "swatch"}
            onChange={(event) =>
              updateGroups(
                groups.map((g, i) =>
                  i === gi ? { ...g, display: event.target.checked ? "swatch" : "pill" } : g,
                ),
              )
            }
          />
          <ul className="flex flex-col gap-2">
            {group.values.map((value, vi) => (
              <li key={value.key} className="flex items-end gap-2">
                <div className="min-w-0 flex-1">
                  <FormField
                    label={t("listings.variants.valueLabel", { number: vi + 1 })}
                    errorMessage={errorText(errors[`groups.${gi}.values.${vi}`])}
                  >
                    <Input
                      value={value.label}
                      data-testid={`variants-value-${gi}-${vi}`}
                      onChange={(event) =>
                        updateGroups(
                          groups.map((g, i) =>
                            i === gi
                              ? {
                                  ...g,
                                  values: g.values.map((v, j) =>
                                    j === vi ? { ...v, label: event.target.value } : v,
                                  ),
                                }
                              : g,
                          ),
                        )
                      }
                    />
                  </FormField>
                </div>
                {group.display === "swatch" ? (
                  <label className="flex min-h-11 flex-col text-xs text-text-2">
                    {t("listings.variants.swatchColour")}
                    <input
                      type="color"
                      className="h-11 w-11 cursor-pointer rounded border border-border"
                      value={value.swatchHex || "#888888"}
                      onChange={(event) =>
                        updateGroups(
                          groups.map((g, i) =>
                            i === gi
                              ? {
                                  ...g,
                                  values: g.values.map((v, j) =>
                                    j === vi ? { ...v, swatchHex: event.target.value } : v,
                                  ),
                                }
                              : g,
                          ),
                        )
                      }
                    />
                  </label>
                ) : null}
                <Button
                  loadingLabel={t("listings.variants.saving")}
                  type="button"
                  variant="ghost"
                  size="sm"
                  aria-label={t("listings.variants.removeValue", { value: value.label || vi + 1 })}
                  onClick={() =>
                    updateGroups(
                      groups.map((g, i) =>
                        i === gi ? { ...g, values: g.values.filter((_, j) => j !== vi) } : g,
                      ),
                    )
                  }
                >
                  {t("listings.variants.remove")}
                </Button>
              </li>
            ))}
          </ul>
          {errors[`groups.${gi}.values`] ? (
            <p className="text-sm text-danger" role="alert">
              {errorText(errors[`groups.${gi}.values`])}
            </p>
          ) : null}
          <div className="flex flex-wrap gap-2">
            <Button
              loadingLabel={t("listings.variants.saving")}
              type="button"
              variant="secondary"
              size="sm"
              data-testid={`variants-add-value-${gi}`}
              onClick={() =>
                updateGroups(
                  groups.map((g, i) =>
                    i === gi
                      ? {
                          ...g,
                          values: [...g.values, { key: newKey("value"), label: "", swatchHex: "" }],
                        }
                      : g,
                  ),
                )
              }
            >
              {t("listings.variants.addValue")}
            </Button>
            <Button
              loadingLabel={t("listings.variants.saving")}
              type="button"
              variant="ghost"
              size="sm"
              onClick={() => updateGroups(groups.filter((_, i) => i !== gi))}
            >
              {t("listings.variants.removeGroup")}
            </Button>
          </div>
        </fieldset>
      ))}

      {groups.length < MAX_GROUPS ? (
        <Button
          loadingLabel={t("listings.variants.saving")}
          type="button"
          variant="secondary"
          data-testid="variants-add-group"
          onClick={() =>
            updateGroups([
              ...groups,
              {
                key: newKey("group"),
                name: "",
                display: groups.length === 0 ? "swatch" : "pill",
                values: [{ key: newKey("value"), label: "", swatchHex: "" }],
              },
            ])
          }
        >
          {groups.length === 0
            ? t("listings.variants.addFirstGroup")
            : t("listings.variants.addGroup")}
        </Button>
      ) : null}

      {rows.length > 0 ? (
        <div className="flex flex-col gap-2">
          <h3 className="text-sm font-medium text-text">
            {t("listings.variants.matrixHeading", { count: rows.length })}
          </h3>
          <p className="text-xs text-text-2">
            {t("listings.variants.priceHint", { price: listingPriceInput })}
          </p>
          <ul className="flex flex-col gap-3" data-testid="variants-matrix">
            {rows.map((row, index) => {
              const label = row.options.join(" / ");
              return (
                <li
                  key={row.options.join("\u0000")}
                  className="flex flex-col gap-2 rounded-lg border border-border p-3"
                  data-testid={`variants-row-${index}`}
                >
                  <div className="flex items-center justify-between gap-2">
                    <p className="font-medium text-text">{label}</p>
                    <Switch
                      label={t("listings.variants.offered")}
                      checked={row.active}
                      onChange={(event) => updateRow(index, { active: event.target.checked })}
                    />
                  </div>
                  <div className="grid grid-cols-2 gap-2">
                    <FormField
                      label={t("listings.variants.sku")}
                      errorMessage={errorText(errors[`variants.${index}.sku`])}
                    >
                      <Input
                        value={row.sku}
                        aria-label={t("listings.variants.skuFor", { variant: label })}
                        onChange={(event) => updateRow(index, { sku: event.target.value })}
                      />
                    </FormField>
                    <FormField
                      label={t("listings.variants.stock")}
                      errorMessage={errorText(errors[`variants.${index}.stock`])}
                    >
                      <Input
                        inputMode="numeric"
                        value={row.stock}
                        aria-label={t("listings.variants.stockFor", { variant: label })}
                        data-testid={`variants-stock-${index}`}
                        onChange={(event) => updateRow(index, { stock: event.target.value })}
                      />
                    </FormField>
                    <FormField
                      label={t("listings.variants.price")}
                      errorMessage={errorText(errors[`variants.${index}.price`])}
                    >
                      <Input
                        inputMode="decimal"
                        value={row.price}
                        placeholder={listingPriceInput}
                        aria-label={t("listings.variants.priceFor", { variant: label })}
                        onChange={(event) => updateRow(index, { price: event.target.value })}
                      />
                    </FormField>
                    <FormField label={t("listings.variants.photo")}>
                      <select
                        className="min-h-11 w-full rounded border border-border bg-bg px-2 text-sm text-text"
                        value={row.imagePublicId}
                        aria-label={t("listings.variants.photoFor", { variant: label })}
                        onChange={(event) =>
                          updateRow(index, { imagePublicId: event.target.value })
                        }
                      >
                        <option value="">{t("listings.variants.photoNone")}</option>
                        {imagePublicIds.map((publicId, position) => (
                          <option key={publicId} value={publicId}>
                            {t("listings.variants.photoOption", { position: position + 1 })}
                          </option>
                        ))}
                      </select>
                    </FormField>
                  </div>
                </li>
              );
            })}
          </ul>
        </div>
      ) : null}

      {errors.variants || errors.groups ? (
        <p className="text-sm text-danger" role="alert">
          {errorText(errors.variants ?? errors.groups)}
        </p>
      ) : null}

      {loadFailed && !status ? (
        <p role="alert" className="text-sm text-danger">
          {t("listings.variants.loadFailed")}
        </p>
      ) : null}

      {status ? (
        <p
          role={status.kind === "error" ? "alert" : "status"}
          className={status.kind === "error" ? "text-sm text-danger" : "text-sm text-success"}
          data-testid="variants-status"
        >
          {status.message}
        </p>
      ) : null}

      <Button
        loadingLabel={t("listings.variants.saving")}
        type="button"
        variant="primary"
        loading={saving}
        disabled={saving}
        data-testid="variants-save"
        onClick={() => void save()}
      >
        {t("listings.variants.save")}
      </Button>
    </section>
  );
}
