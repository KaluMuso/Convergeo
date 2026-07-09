"use client";

import { useEffect, useState } from "react";

import { Button, FormField, Input, Select, Spinner } from "../_lib/ui";

import { CommissionBanner } from "./commission-banner";
import {
  ListingFields,
  parseListingFieldValues,
  validateListingFields,
  type ListingFieldValues,
} from "./listing-fields";

import type { createListingClient } from "../_lib/listing-client";
import type { CategoryOption } from "../_lib/types";

type ListingClient = ReturnType<typeof createListingClient>;

const DEFAULT_FIELDS: ListingFieldValues = {
  priceZmw: "",
  condition: "new",
  stockMode: "tracked",
  stockQty: "1",
  wholesale: false,
  moq: "10",
};

type NewCanonicalFormProps = {
  client: ListingClient;
  wholesaleEnabled: boolean;
  onSuccess: (listingId: string) => void;
  onError: (message: string) => void;
  labels: {
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
  const [categories, setCategories] = useState<CategoryOption[]>([]);
  const [loadingCategories, setLoadingCategories] = useState(true);
  const [productName, setProductName] = useState("");
  const [brand, setBrand] = useState("");
  const [categoryId, setCategoryId] = useState("");
  const [fields, setFields] = useState<ListingFieldValues>(DEFAULT_FIELDS);
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
    if (!productName.trim() || !categoryId) {
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
        mode: "new_canonical",
        product_name: productName.trim(),
        brand: brand.trim() || null,
        category_id: categoryId,
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

      <FormField label={labels.categoryLabel} required requiredMarker="*">
        <Select value={categoryId} onChange={(event) => setCategoryId(event.target.value)}>
          <option value="">{labels.categoryPlaceholder}</option>
          {categories.map((category) => (
            <option key={category.id} value={category.id}>
              {category.name}
            </option>
          ))}
        </Select>
      </FormField>

      {selectedCategory ? (
        <CommissionBanner
          commission={selectedCategory.commission}
          categoryName={selectedCategory.name}
          labels={labels.commission}
        />
      ) : null}

      <ListingFields
        values={fields}
        onChange={(patch) => setFields((current) => ({ ...current, ...patch }))}
        wholesaleEnabled={wholesaleEnabled}
        labels={labels.fields}
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
