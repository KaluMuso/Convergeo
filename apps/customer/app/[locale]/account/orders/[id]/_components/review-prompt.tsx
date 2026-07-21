"use client";

import { ApiError, createApiClient } from "@vergeo/config";
import { Button } from "@vergeo/ui/src/button";
import { FormField } from "@vergeo/ui/src/form-field";
import { useRouter } from "next/navigation";
import { useCallback, useEffect, useState } from "react";

import { getApiBaseUrl } from "../../../../../../lib/api-base-url";

export type ReviewPromptLabels = {
  title: string;
  body: string;
  itemLabel: string;
  ratingLabel: string;
  starsAria: string;
  bodyLabel: string;
  bodyPlaceholder: string;
  submit: string;
  submitting: string;
  success: string;
  error: string;
  editNotice: string;
  loading: string;
  starFilled: string;
  starEmpty: string;
};

type OrderReviewItem = {
  order_item_id: string;
  title: string;
  review_id: string | null;
  rating: number | null;
  can_review: boolean;
  can_edit: boolean;
};

type ReviewPromptBlockProps = {
  orderId: string;
  accessToken: string;
  status: string;
  labels: ReviewPromptLabels;
};

type ReviewResponse = {
  id: string;
  order_item_id: string;
  rating: number;
};

function StarPicker({
  value,
  onChange,
  ariaLabel,
  starFilled,
  starEmpty,
}: {
  value: number;
  onChange: (rating: number) => void;
  ariaLabel: string;
  starFilled: string;
  starEmpty: string;
}) {
  return (
    <div className="flex gap-1" role="radiogroup" aria-label={ariaLabel}>
      {Array.from({ length: 5 }, (_, index) => {
        const rating = index + 1;
        const selected = rating <= value;
        return (
          <button
            key={rating}
            type="button"
            role="radio"
            aria-checked={selected}
            className={`min-h-11 min-w-11 text-xl ${selected ? "text-warning" : "text-text-3"}`}
            onClick={() => onChange(rating)}
          >
            {selected ? starFilled : starEmpty}
          </button>
        );
      })}
    </div>
  );
}

export function ReviewPromptBlock({
  orderId,
  accessToken,
  status,
  labels,
}: ReviewPromptBlockProps) {
  const router = useRouter();
  const [items, setItems] = useState<OrderReviewItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [activeItemId, setActiveItemId] = useState<string | undefined>();
  const [rating, setRating] = useState(5);
  const [body, setBody] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | undefined>();
  const [success, setSuccess] = useState(false);

  const reviewable = status === "delivered" || status === "completed";

  const loadItems = useCallback(async () => {
    if (!reviewable) {
      setLoading(false);
      return;
    }
    try {
      const client = createApiClient({
        baseUrl: getApiBaseUrl(),
        getToken: () => accessToken,
      });
      const rows = await client.request<OrderReviewItem[]>(`/reviews/order/${orderId}`);
      const actionable = rows.filter((row) => row.can_review || row.can_edit);
      setItems(actionable);
      if (actionable.length > 0) {
        const first = actionable[0]!;
        setActiveItemId(first.order_item_id);
        if (first.rating) {
          setRating(first.rating);
        }
      }
    } catch {
      setError(labels.error);
    } finally {
      setLoading(false);
    }
  }, [accessToken, labels.error, orderId, reviewable]);

  useEffect(() => {
    void loadItems();
  }, [loadItems]);

  const handleSubmit = useCallback(async () => {
    if (!activeItemId || submitting) {
      return;
    }
    setSubmitting(true);
    setError(undefined);
    try {
      const client = createApiClient({
        baseUrl: getApiBaseUrl(),
        getToken: () => accessToken,
      });
      await client.request<ReviewResponse>("/reviews", {
        method: "POST",
        body: JSON.stringify({
          order_item_id: activeItemId,
          rating,
          body: body.trim() || null,
          photos: [],
        }),
      });
      setSuccess(true);
      router.refresh();
    } catch (caught) {
      if (caught instanceof ApiError) {
        setError(labels.error);
      } else {
        setError(labels.error);
      }
    } finally {
      setSubmitting(false);
    }
  }, [accessToken, activeItemId, body, labels.error, rating, router, submitting]);

  if (!reviewable || loading) {
    if (loading && reviewable) {
      return <p className="text-sm text-text-2">{labels.loading}</p>;
    }
    return null;
  }

  if (items.length === 0) {
    return null;
  }

  const activeItem = items.find((item) => item.order_item_id === activeItemId) ?? items[0];

  return (
    <section
      aria-labelledby="review-prompt-heading"
      className="space-y-4 rounded border border-border bg-surface p-4"
    >
      <header className="space-y-1">
        <h3 id="review-prompt-heading" className="font-display text-h3 text-display-ink">
          {labels.title}
        </h3>
        <p className="text-sm text-text-2">{labels.body}</p>
      </header>

      {items.length > 1 ? (
        <FormField label={labels.itemLabel} id="review-item-select">
          <select
            className="min-h-11 w-full rounded border border-border bg-bg px-3 text-sm"
            value={activeItem?.order_item_id}
            onChange={(event) => {
              const next = items.find((item) => item.order_item_id === event.target.value);
              setActiveItemId(event.target.value);
              setRating(next?.rating ?? 5);
              setSuccess(false);
            }}
          >
            {items.map((item) => (
              <option key={item.order_item_id} value={item.order_item_id}>
                {item.title}
              </option>
            ))}
          </select>
        </FormField>
      ) : (
        <p className="text-sm font-medium text-display-ink">{activeItem?.title}</p>
      )}

      {activeItem?.can_edit ? <p className="text-sm text-text-2">{labels.editNotice}</p> : null}

      {success ? (
        <p className="text-sm font-medium text-display-ink">{labels.success}</p>
      ) : (
        <>
          <FormField label={labels.ratingLabel} id="review-rating">
            <div>
              <StarPicker
                value={rating}
                onChange={setRating}
                ariaLabel={labels.starsAria.replace("{rating}", String(rating))}
                starFilled={labels.starFilled}
                starEmpty={labels.starEmpty}
              />
            </div>
          </FormField>

          <FormField label={labels.bodyLabel} id="review-body">
            <textarea
              className="min-h-24 w-full rounded border border-border bg-bg px-3 py-2 text-sm"
              placeholder={labels.bodyPlaceholder}
              value={body}
              onChange={(event) => setBody(event.target.value)}
              maxLength={4000}
            />
          </FormField>

          {error ? (
            <p className="text-sm text-error" role="alert">
              {error}
            </p>
          ) : null}

          <Button
            type="button"
            className="min-h-11 w-full"
            disabled={submitting}
            loading={submitting}
            loadingLabel={labels.submitting}
            onClick={() => void handleSubmit()}
          >
            {labels.submit}
          </Button>
        </>
      )}
    </section>
  );
}
