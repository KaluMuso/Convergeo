"use client";

import { useEffect, useRef, useState } from "react";

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
  onRequestCatalog: () => void;
  labels: {
    heading: string;
    intro: string;
    titleLabel: string;
    titlePlaceholder: string;
    categoryLabel: string;
    categoryPlaceholder: string;
    descriptionLabel: string;
    descriptionHelp: string;
    descriptionInvalid: string;
    saveDraft: string;
    savingDraft: string;
    draftNotice: string;
    canonicalRequired: string;
    catalogLabel: string;
    categoriesUnavailable: string;
    fields: Parameters<typeof ListingFields>[0]["labels"];
    submitError: string;
    standaloneRequired: string;
    required: string;
  };
};

export function QuickListForm({
  client,
  wholesaleEnabled,
  onSuccess,
  onError,
  onRequestCatalog,
  labels,
}: QuickListFormProps) {
  const [title, setTitle] = useState("");
  const [description, setDescription] = useState("");
  const [categoryId, setCategoryId] = useState("");
  const [categories, setCategories] = useState<CategoryOption[]>([]);
  const [categoryStatus, setCategoryStatus] = useState<"loading" | "ready" | "error">("loading");
  const [fields, setFields] = useState<ListingFieldValues>(DEFAULT_FIELDS);
  const [submitting, setSubmitting] = useState(false);
  const submissionInFlight = useRef(false);
  const standalone = fields.productClass === "D" || fields.productClass === "E";

  useEffect(() => {
    let cancelled = false;
    setCategoryStatus("loading");
    setCategories([]);
    setCategoryId("");
    void client.listCategories().then(
      (items) => {
        if (!cancelled) {
          setCategories(items);
          setCategoryStatus("ready");
        }
      },
      () => {
        if (!cancelled) setCategoryStatus("error");
      },
    );
    return () => {
      cancelled = true;
    };
  }, [client]);

  const handleSaveDraft = async () => {
    if (submissionInFlight.current) return;
    if (!standalone) {
      onError(labels.canonicalRequired);
      return;
    }
    if (categoryStatus !== "ready" || categories.length === 0) {
      onError(labels.categoriesUnavailable);
      return;
    }
    if (!title.trim() || !categories.some((category) => category.id === categoryId)) {
      onError(labels.required);
      return;
    }
    if (Array.from(description.trim()).length < 20) {
      onError(labels.descriptionInvalid);
      return;
    }
    const validationError = validateListingFields(fields, labels.fields);
    if (validationError) {
      onError(validationError);
      return;
    }
    if (fields.condition === "used" && Array.from(fields.defectNotes.trim()).length < 10) {
      onError(labels.fields.defectNotesInvalid);
      return;
    }
    const parsed = parseListingFieldValues(fields);
    if (
      fields.productClass === "E" &&
      (parsed.vendorCapacityPerWeek ?? 0) < Math.max(parsed.minSteps, parsed.moq)
    ) {
      onError(labels.fields.capacityInvalid);
      return;
    }

    submissionInFlight.current = true;
    setSubmitting(true);
    try {
      const requiresEvidence = requiresListingEvidence(fields);
      const response = await client.createListing({
        mode: "quick_list",
        product_id: null,
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
          fallback: labels.submitError,
        }),
      );
    } finally {
      submissionInFlight.current = false;
      setSubmitting(false);
    }
  };

  return (
    <div className="flex flex-col gap-4">
      <header className="space-y-1">
        <h2 className="font-display text-h4 text-display-ink">{labels.heading}</h2>
        <p className="text-sm text-text-2">{labels.intro}</p>
      </header>

      {!standalone ? (
        <div className="space-y-2">
          <p role="note" className="text-sm text-text-2">
            {labels.canonicalRequired}
          </p>
          <Button variant="secondary" loadingLabel={labels.catalogLabel} onClick={onRequestCatalog}>
            {labels.catalogLabel}
          </Button>
        </div>
      ) : null}

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
              disabled={categoryStatus !== "ready" || submitting}
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
          {categoryStatus === "error" || (categoryStatus === "ready" && categories.length === 0) ? (
            <p role="alert" className="text-sm text-danger">
              {labels.categoriesUnavailable}
            </p>
          ) : null}
          <FormField
            label={labels.descriptionLabel}
            helpText={labels.descriptionHelp}
            required
            requiredMarker="*"
          >
            <Textarea
              value={description}
              onChange={(event) => setDescription(event.target.value)}
            />
          </FormField>
          <p role="note" className="text-sm text-text-2">
            {labels.draftNotice}
          </p>
        </>
      ) : null}

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
        disabled={!standalone || categoryStatus !== "ready" || categories.length === 0}
        loadingLabel={labels.savingDraft}
        onClick={() => void handleSaveDraft()}
      >
        {labels.saveDraft}
      </Button>
    </div>
  );
}
