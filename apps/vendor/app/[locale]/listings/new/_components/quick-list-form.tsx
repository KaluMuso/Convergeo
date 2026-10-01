"use client";

import { useEffect, useState } from "react";

import { listingCreateErrorMessage } from "../_lib/listing-errors";
import { Button, FormField, Input, Select, Textarea } from "../_lib/ui";

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

const DEFAULT_FIELDS: ListingFieldValues = {
  ...DEFAULT_LISTING_FIELDS,
  productClass: "C",
  stockMode: "always_available",
  stockQty: "",
};

type QuickListFormProps = {
  client: ListingClient;
  wholesaleEnabled: boolean;
  onSuccess: (response: ListingCreateResponse, requiresEvidence: boolean) => void;
  onError: (message: string) => void;
  labels: {
    heading: string;
    intro: string;
    titleLabel: string;
    titlePlaceholder: string;
    publish: string;
    publishing: string;
    fields: Parameters<typeof ListingFields>[0]["labels"];
    submitError: string;
    standaloneRequired: string;
    canonicalRequired: string;
    standaloneDetailsRequired: string;
    policyBlocked: string;
    categoryLabel: string;
    categoryPlaceholder: string;
    descriptionLabel: string;
    descriptionHelp: string;
    draftNotice: string;
    required: string;
  };
};

export function QuickListForm({
  client,
  wholesaleEnabled,
  onSuccess,
  onError,
  labels,
}: QuickListFormProps) {
  const [title, setTitle] = useState("");
  const [fields, setFields] = useState<ListingFieldValues>(DEFAULT_FIELDS);
  const [submitting, setSubmitting] = useState(false);
  const [categoryId, setCategoryId] = useState("");
  const [description, setDescription] = useState("");
  const [categories, setCategories] = useState<CategoryOption[]>([]);
  const [loadingCategories, setLoadingCategories] = useState(false);
  const standalone = fields.productClass === "D" || fields.productClass === "E";

  useEffect(() => {
    if (!standalone) return;
    let cancelled = false;
    setLoadingCategories(true);
    void client
      .listCategories()
      .then((items) => {
        if (!cancelled) setCategories(items);
      })
      .catch(() => {
        if (!cancelled) onError(labels.submitError);
      })
      .finally(() => {
        if (!cancelled) setLoadingCategories(false);
      });
    return () => {
      cancelled = true;
    };
  }, [client, labels.submitError, onError, standalone]);

  const handlePublish = async () => {
    if (!title.trim()) {
      onError(labels.required);
      return;
    }
    if (!standalone) {
      onError(labels.canonicalRequired);
      return;
    }
    if (!categoryId || description.trim().length < 20) {
      onError(labels.standaloneDetailsRequired);
      return;
    }
    const validationError = validateListingFields(fields, labels.fields);
    if (validationError) {
      onError(validationError);
      return;
    }

    setSubmitting(true);
    try {
      const parsed = parseListingFieldValues(fields);
      const requiresEvidence = requiresListingEvidence(fields);
      const response = await client.createListing({
        mode: "quick_list",
        title_override: title.trim(),
        category_id: categoryId,
        description: description.trim(),
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
        publish: false,
      });
      onSuccess(response, response.requires_evidence ?? requiresEvidence);
    } catch (caught: unknown) {
      onError(
        listingCreateErrorMessage(caught, {
          standaloneRequired: labels.standaloneRequired,
          canonicalRequired: labels.canonicalRequired,
          standaloneDetailsRequired: labels.standaloneDetailsRequired,
          policyBlocked: labels.policyBlocked,
          fallback: labels.submitError,
        }),
      );
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="flex flex-col gap-4">
      <header className="space-y-1">
        <h2 className="font-display text-h4 text-display-ink">{labels.heading}</h2>
        <p className="text-sm text-text-2">{labels.intro}</p>
      </header>

      <FormField label={labels.titleLabel} required requiredMarker="*">
        <Input
          value={title}
          onChange={(event) => setTitle(event.target.value)}
          placeholder={labels.titlePlaceholder}
        />
      </FormField>

      {standalone ? (
        <>
          <FormField label={labels.categoryLabel} required requiredMarker="*">
            <Select
              value={categoryId}
              disabled={loadingCategories}
              onChange={(event) => setCategoryId(event.target.value)}
            >
              <option value="">{labels.categoryPlaceholder}</option>
              {categories.map((category) => (
                <option key={category.id} value={category.id}>
                  {category.name}
                </option>
              ))}
            </Select>
          </FormField>
          <FormField
            label={labels.descriptionLabel}
            helpText={labels.descriptionHelp}
            required
            requiredMarker="*"
          >
            <Textarea
              value={description}
              maxLength={5000}
              onChange={(event) => setDescription(event.target.value)}
            />
          </FormField>
          <p className="text-sm text-text-2">{labels.draftNotice}</p>
        </>
      ) : (
        <p className="text-sm text-text-2">{labels.canonicalRequired}</p>
      )}

      <ListingFields
        values={fields}
        onChange={(patch) => setFields((current) => ({ ...current, ...patch }))}
        wholesaleEnabled={wholesaleEnabled}
        labels={labels.fields}
        allowStandaloneClasses
      />

      <Button
        type="button"
        size="lg"
        className="w-full"
        loading={submitting}
        disabled={loadingCategories}
        loadingLabel={labels.fields.savingDraft}
        onClick={() => void handlePublish()}
      >
        {standalone ? labels.fields.saveDraft : labels.publish}
      </Button>
    </div>
  );
}
