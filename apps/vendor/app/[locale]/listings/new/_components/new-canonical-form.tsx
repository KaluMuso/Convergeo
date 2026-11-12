"use client";

import { CategorySelection, categoryPath } from "@vergeo/ui/src/category-selection";
import { useTranslations } from "next-intl";
import { useEffect, useState } from "react";

import { listingCreateErrorMessage } from "../_lib/listing-errors";
import { Button, FormField, Input, Spinner } from "../_lib/ui";

import { buildCanonicalSpec, type DetailEntry } from "./canonical-details";
import { CanonicalDetailsFields, type CanonicalDetailsLabels } from "./canonical-details-fields";
import { CommissionBanner } from "./commission-banner";
import {
  DEFAULT_LISTING_FIELDS,
  ListingFields,
  parseListingFieldValues,
  requiresListingEvidence,
  validateListingFields,
  type ListingFieldValues,
} from "./listing-fields";

import type { createListingClient } from "../_lib/listing-client";
import type { CategoryOption, ListingCreateResponse } from "../_lib/types";

type ListingClient = ReturnType<typeof createListingClient>;

type NewCanonicalFormProps = {
  client: ListingClient;
  wholesaleEnabled: boolean;
  onSuccess: (response: ListingCreateResponse, requiresEvidence: boolean) => void;
  onError: (message: string) => void;
  labels: {
    details: CanonicalDetailsLabels;
    heading: string;
    intro: string;
    nameLabel: string;
    namePlaceholder: string;
    brandLabel: string;
    brandPlaceholder: string;
    categoryLabel: string;
    categoryPlaceholder: string;
    submit: string;
    submitting: string;
    moderationNotice: string;
    fields: Parameters<typeof ListingFields>[0]["labels"];
    commission: Parameters<typeof CommissionBanner>[0]["labels"];
    submitError: string;
    standaloneRequired: string;
    required: string;
  };
};

export function NewCanonicalForm({
  client,
  wholesaleEnabled,
  onSuccess,
  onError,
  labels,
}: NewCanonicalFormProps) {
  const taxonomyText = useTranslations("common.categorySelection");
  const [categories, setCategories] = useState<CategoryOption[]>([]);
  const [loadingCategories, setLoadingCategories] = useState(true);
  const [productName, setProductName] = useState("");
  const [description, setDescription] = useState("");
  const [details, setDetails] = useState<DetailEntry[]>([]);
  const [brand, setBrand] = useState("");
  const [categoryId, setCategoryId] = useState("");
  const [fields, setFields] = useState<ListingFieldValues>(DEFAULT_LISTING_FIELDS);
  const [submitting, setSubmitting] = useState(false);

  useEffect(() => {
    let cancelled = false;
    void client
      .listCategories()
      .then((items) => {
        if (!cancelled) {
          setCategories(items);
        }
      })
      .catch(() => {
        if (!cancelled) {
          onError(labels.submitError);
        }
      })
      .finally(() => {
        if (!cancelled) {
          setLoadingCategories(false);
        }
      });
    return () => {
      cancelled = true;
    };
  }, [client, labels.submitError, onError]);

  const selectedCategory = categories.find((item) => item.id === categoryId) ?? null;

  const handleSubmit = async () => {
    if (
      !productName.trim() ||
      !categoryPath(
        categories.map((item) => ({
          id: item.id,
          parentId: item.parent_id ?? null,
          label: item.name,
        })),
        categoryId,
      ).length
    ) {
      onError(labels.required);
      return;
    }
    const validationError = validateListingFields(fields, labels.fields);
    if (validationError) {
      onError(validationError);
      return;
    }

    const spec = buildCanonicalSpec(details);
    if (spec === null || description.length > 5000) {
      onError(labels.details.invalid);
      return;
    }
    setSubmitting(true);
    try {
      const parsed = parseListingFieldValues(fields);
      const response = await client.createListing({
        mode: "new_canonical",
        product_name: productName.trim(),
        brand: brand.trim() || null,
        description: description.trim(),
        spec,
        category_id: categoryId,
        price_ngwee: parsed.priceNgwee,
        product_class: fields.productClass,
        sale_unit: fields.saleUnit,
        unit_step_milli: parsed.unitStepMilli,
        min_steps: parsed.minSteps,
        condition: fields.condition,
        defect_notes: parsed.defectNotes,
        fulfilment_mode: fields.fulfilmentMode,
        lead_time_days: parsed.leadTimeDays,
        vendor_capacity_per_week: parsed.vendorCapacityPerWeek,
        stock_mode: fields.stockMode,
        stock_qty: parsed.stockQty,
        wholesale: fields.wholesale,
        moq: parsed.moq,
        publish: !requiresListingEvidence(fields),
      });
      onSuccess(response, response.requires_evidence ?? requiresListingEvidence(fields));
    } catch (caught: unknown) {
      onError(
        listingCreateErrorMessage(caught, {
          standaloneRequired: labels.standaloneRequired,
          fallback: labels.submitError,
        }),
      );
    } finally {
      setSubmitting(false);
    }
  };

  if (loadingCategories) {
    return <Spinner label={labels.submitting} />;
  }

  return (
    <div className="flex flex-col gap-4">
      <header className="space-y-1">
        <h2 className="font-display text-h4 text-display-ink">{labels.heading}</h2>
        <p className="text-sm text-text-2">{labels.intro}</p>
      </header>

      <FormField label={labels.nameLabel} required requiredMarker="*">
        <Input
          value={productName}
          onChange={(event) => setProductName(event.target.value)}
          placeholder={labels.namePlaceholder}
        />
      </FormField>

      <FormField label={labels.brandLabel}>
        <Input
          value={brand}
          onChange={(event) => setBrand(event.target.value)}
          placeholder={labels.brandPlaceholder}
        />
      </FormField>

      <CategorySelection
        nodes={categories.map((item) => ({
          id: item.id,
          parentId: item.parent_id ?? null,
          label: item.name,
        }))}
        value={categoryId}
        onChange={setCategoryId}
        disabled={loadingCategories || submitting}
        labels={{
          category: labels.categoryLabel,
          subcategory: taxonomyText("subcategory"),
          placeholder: labels.categoryPlaceholder,
          empty: taxonomyText("empty"),
          unavailable: taxonomyText("unavailable"),
        }}
      />

      {selectedCategory ? (
        <CommissionBanner
          commission={selectedCategory.commission}
          categoryName={selectedCategory.name}
          labels={labels.commission}
        />
      ) : null}

      <CanonicalDetailsFields
        description={description}
        entries={details}
        onDescription={setDescription}
        onEntries={setDetails}
        labels={labels.details}
      />

      <ListingFields
        values={fields}
        onChange={(patch) => setFields((current) => ({ ...current, ...patch }))}
        wholesaleEnabled={wholesaleEnabled}
        labels={labels.fields}
        allowStandaloneClasses={false}
      />

      <p className="text-sm text-text-2">{labels.moderationNotice}</p>

      <Button
        type="button"
        size="lg"
        className="w-full"
        loading={submitting}
        loadingLabel={labels.submitting}
        onClick={() => void handleSubmit()}
      >
        {labels.submit}
      </Button>
    </div>
  );
}
