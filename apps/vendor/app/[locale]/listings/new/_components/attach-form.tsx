"use client";

import { useEffect, useState } from "react";

import { listingCreateErrorMessage } from "../_lib/listing-errors";
import { Button, Spinner } from "../_lib/ui";

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
import type { CanonicalPreview, ListingCreateResponse } from "../_lib/types";

type ListingClient = ReturnType<typeof createListingClient>;

type AttachFormProps = {
  client: ListingClient;
  productId: string;
  wholesaleEnabled: boolean;
  onSuccess: (response: ListingCreateResponse, requiresEvidence: boolean) => void;
  onError: (message: string) => void;
  labels: {
    specHeading: string;
    publish: string;
    publishing: string;
    fields: Parameters<typeof ListingFields>[0]["labels"];
    commission: Parameters<typeof CommissionBanner>[0]["labels"];
    submitError: string;
    standaloneRequired: string;
  };
};

export function AttachForm({
  client,
  productId,
  wholesaleEnabled,
  onSuccess,
  onError,
  labels,
}: AttachFormProps) {
  const [preview, setPreview] = useState<CanonicalPreview | null>(null);
  const [loadingPreview, setLoadingPreview] = useState(true);
  const [fields, setFields] = useState<ListingFieldValues>(DEFAULT_LISTING_FIELDS);
  const [submitting, setSubmitting] = useState(false);

  useEffect(() => {
    let cancelled = false;
    setLoadingPreview(true);
    void client
      .getCanonicalPreview(productId)
      .then((data) => {
        if (!cancelled) {
          setPreview(data);
        }
      })
      .catch(() => {
        if (!cancelled) {
          onError(labels.submitError);
        }
      })
      .finally(() => {
        if (!cancelled) {
          setLoadingPreview(false);
        }
      });
    return () => {
      cancelled = true;
    };
  }, [client, labels.submitError, onError, productId]);

  const handlePublish = async () => {
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
        mode: "attach",
        product_id: productId,
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

  if (loadingPreview) {
    return <Spinner label={labels.publishing} />;
  }

  if (!preview) {
    return null;
  }

  const specEntries = Object.entries(preview.spec);

  return (
    <div className="flex flex-col gap-4">
      <header className="space-y-1">
        <h2 className="font-display text-h4 text-display-ink">{preview.name}</h2>
        {preview.brand ? <p className="text-sm text-text-2">{preview.brand}</p> : null}
      </header>

      <CommissionBanner
        commission={preview.commission}
        categoryName={preview.category_name}
        labels={labels.commission}
      />

      {specEntries.length > 0 ? (
        <section className="rounded-lg border border-border p-3">
          <h3 className="mb-2 text-sm font-medium text-text">{labels.specHeading}</h3>
          <dl className="grid grid-cols-2 gap-2 text-sm">
            {specEntries.map(([key, value]) => (
              <div key={key}>
                <dt className="text-text-3">{key}</dt>
                <dd className="text-text">{String(value)}</dd>
              </div>
            ))}
          </dl>
        </section>
      ) : null}

      <ListingFields
        values={fields}
        onChange={(patch) => setFields((current) => ({ ...current, ...patch }))}
        wholesaleEnabled={wholesaleEnabled}
        labels={labels.fields}
        allowStandaloneClasses={false}
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
