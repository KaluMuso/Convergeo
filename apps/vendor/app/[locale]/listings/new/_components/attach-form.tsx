"use client";

import { useEffect, useState } from "react";

import { Button, Spinner } from "../_lib/ui";

import { CommissionBanner } from "./commission-banner";
import {
  ListingFields,
  parseListingFieldValues,
  validateListingFields,
  type ListingFieldValues,
} from "./listing-fields";

import type { createListingClient } from "../_lib/listing-client";
import type { CanonicalPreview } from "../_lib/types";

type ListingClient = ReturnType<typeof createListingClient>;

const DEFAULT_FIELDS: ListingFieldValues = {
  priceZmw: "",
  condition: "new",
  stockMode: "tracked",
  stockQty: "1",
  wholesale: false,
  moq: "10",
};

type AttachFormProps = {
  client: ListingClient;
  productId: string;
  wholesaleEnabled: boolean;
  onSuccess: (listingId: string) => void;
  onError: (message: string) => void;
  labels: {
    specHeading: string;
    publish: string;
    publishing: string;
    fields: Parameters<typeof ListingFields>[0]["labels"];
    commission: Parameters<typeof CommissionBanner>[0]["labels"];
    submitError: string;
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
  const [fields, setFields] = useState<ListingFieldValues>(DEFAULT_FIELDS);
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
      const response = await client.createListing({
        mode: "attach",
        product_id: productId,
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
