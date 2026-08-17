"use client";

import { useState } from "react";

import { listingCreateErrorMessage } from "../_lib/listing-errors";
import { Button, FormField, Input } from "../_lib/ui";

import {
  DEFAULT_LISTING_FIELDS,
  ListingFields,
  parseListingFieldValues,
  requiresListingEvidence,
  validateListingFields,
  type ListingFieldValues,
} from "./listing-fields";

import type { createListingClient } from "../_lib/listing-client";
import type { ListingCreateResponse } from "../_lib/types";

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

  const handlePublish = async () => {
    if (!title.trim()) {
      onError(labels.required);
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
        price_ngwee: parsed.priceNgwee,
        product_class: fields.productClass,
        sale_unit: fields.saleUnit,
        unit_step_milli: parsed.unitStepMilli,
        min_steps: parsed.minSteps,
        condition: fields.condition,
        condition_detail: fields.conditionDetail,
        pricing_mode: fields.pricingMode,
        defect_notes: parsed.defectNotes,
        fulfilment_mode: fields.fulfilmentMode,
        lead_time_days: parsed.leadTimeDays,
        vendor_capacity_per_week: parsed.vendorCapacityPerWeek,
        stock_mode: fields.stockMode,
        stock_qty: parsed.stockQty,
        wholesale: fields.wholesale,
        moq: parsed.moq,
        publish: !requiresEvidence,
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
        loadingLabel={
          requiresListingEvidence(fields) ? labels.fields.savingDraft : labels.publishing
        }
        onClick={() => void handlePublish()}
      >
        {requiresListingEvidence(fields) ? labels.fields.saveDraft : labels.publish}
      </Button>
    </div>
  );
}
