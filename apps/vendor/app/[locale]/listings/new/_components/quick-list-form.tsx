"use client";

import { useState } from "react";

import { Button, FormField, Input } from "../_lib/ui";

import {
  ListingFields,
  parseListingFieldValues,
  validateListingFields,
  type ListingFieldValues,
} from "./listing-fields";

import type { createListingClient } from "../_lib/listing-client";

type ListingClient = ReturnType<typeof createListingClient>;

const DEFAULT_FIELDS: ListingFieldValues = {
  priceZmw: "",
  condition: "new",
  stockMode: "always_available",
  stockQty: "",
  wholesale: false,
  moq: "10",
};

type QuickListFormProps = {
  client: ListingClient;
  wholesaleEnabled: boolean;
  onSuccess: (listingId: string) => void;
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
      const response = await client.createListing({
        mode: "quick_list",
        title_override: title.trim(),
        price_ngwee: parsed.priceNgwee,
        condition: fields.condition,
        stock_mode: fields.stockMode,
        stock_qty: parsed.stockQty,
        wholesale: fields.wholesale,
        moq: parsed.moq,
        publish: true,
      });
      onSuccess(response.listing_id);
    } catch {
      onError(labels.submitError);
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
      />

      <Button
        type="button"
        size="lg"
        className="w-full"
        loading={submitting}
        loadingLabel={labels.publishing}
        onClick={() => void handlePublish()}
      >
        {labels.publish}
      </Button>
    </div>
  );
}
