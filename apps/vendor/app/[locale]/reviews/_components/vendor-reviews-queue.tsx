"use client";

import { useSession } from "@vergeo/auth/use-session";
import { ApiError, createApiClient } from "@vergeo/config";
import { useTranslations } from "next-intl";
import { useCallback, useEffect, useState } from "react";

import { CloudinaryImage } from "../../../../../../packages/ui/src/media/cloudinary-image";
import { getApiBaseUrl } from "../../../../lib/api-base-url";
import { Button } from "../../listings/new/_lib/ui";

type VendorReviewRow = {
  id: string;
  order_item_id: string;
  rating: number;
  body: string | null;
  photos: string[];
  vendor_reply: string | null;
  vendor_reply_at: string | null;
  reply_editable_until: string | null;
  item_title: string | null;
  created_at: string;
};

function StarRow({
  rating,
  starFilled,
  starEmpty,
}: {
  rating: number;
  starFilled: string;
  starEmpty: string;
}) {
  return (
    <div className="flex items-center gap-0.5" aria-hidden="true">
      {Array.from({ length: 5 }, (_, index) => (
        <span key={index} className={index < rating ? "text-warning" : "text-text-3"}>
          {index < rating ? starFilled : starEmpty}
        </span>
      ))}
    </div>
  );
}

export function VendorReviewsQueue() {
  const t = useTranslations("vendor.reviews");
  const { session } = useSession();
  const [reviews, setReviews] = useState<VendorReviewRow[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | undefined>();
  const [drafts, setDrafts] = useState<Record<string, string>>({});
  const [actingId, setActingId] = useState<string | null>(null);

  const loadReviews = useCallback(async () => {
    const token = session?.access_token;
    if (!token) {
      setLoading(false);
      return;
    }
    setError(undefined);
    try {
      const client = createApiClient({
        baseUrl: getApiBaseUrl(),
        getToken: () => token,
      });
      const rows = await client.request<VendorReviewRow[]>("/reviews/vendor");
      setReviews(rows);
      setDrafts(Object.fromEntries(rows.map((row) => [row.id, row.vendor_reply ?? ""])));
    } catch (caught) {
      if (caught instanceof ApiError) {
        setError(t("errors.loadFailed"));
      } else {
        setError(t("errors.loadFailed"));
      }
    } finally {
      setLoading(false);
    }
  }, [session?.access_token, t]);

  useEffect(() => {
    void loadReviews();
  }, [loadReviews]);

  const submitReply = useCallback(
    async (reviewId: string) => {
      const token = session?.access_token;
      const reply = drafts[reviewId]?.trim();
      if (!token || !reply || actingId) {
        return;
      }
      setActingId(reviewId);
      setError(undefined);
      try {
        const client = createApiClient({
          baseUrl: getApiBaseUrl(),
          getToken: () => token,
        });
        const updated = await client.request<VendorReviewRow>(`/reviews/${reviewId}/reply`, {
          method: "POST",
          body: JSON.stringify({ reply }),
        });
        setReviews((current) =>
          current.map((row) => (row.id === reviewId ? { ...row, ...updated } : row)),
        );
      } catch {
        setError(t("errors.replyFailed"));
      } finally {
        setActingId(null);
      }
    },
    [actingId, drafts, session?.access_token, t],
  );

  if (loading) {
    return <p className="text-sm text-text-2">{t("loading")}</p>;
  }

  return (
    <div className="space-y-4">
      <header className="space-y-1">
        <h1 className="font-display text-h2 text-display-ink">{t("title")}</h1>
        <p className="text-sm text-text-2">{t("intro")}</p>
      </header>

      {error ? (
        <p className="text-sm text-error" role="alert">
          {error}
        </p>
      ) : null}

      {reviews.length === 0 ? (
        <p className="text-sm text-text-2">{t("empty")}</p>
      ) : (
        <ul className="space-y-4">
          {reviews.map((review) => {
            const hasReply = Boolean(review.vendor_reply);
            const replyEditable =
              !hasReply ||
              (review.reply_editable_until
                ? Date.parse(review.reply_editable_until) > Date.now()
                : true);
            return (
              <li key={review.id} className="space-y-3 rounded border border-border bg-surface p-4">
                <div className="space-y-1">
                  <p className="text-sm font-medium text-display-ink">
                    {review.item_title ?? t("card.unknownItem")}
                  </p>
                  <StarRow
                    rating={review.rating}
                    starFilled={t("starFilled")}
                    starEmpty={t("starEmpty")}
                  />
                  {review.body ? <p className="text-sm text-text-2">{review.body}</p> : null}
                </div>

                {review.photos.length > 0 ? (
                  <div className="flex flex-wrap gap-2">
                    {review.photos.map((publicId) => (
                      <CloudinaryImage
                        key={publicId}
                        publicId={publicId}
                        alt={t("card.photoAlt")}
                        ratio={1}
                        width={128}
                        className="h-16 w-16"
                      />
                    ))}
                  </div>
                ) : null}

                {replyEditable ? (
                  <div className="space-y-2">
                    <label
                      htmlFor={`reply-${review.id}`}
                      className="text-sm font-medium text-display-ink"
                    >
                      {hasReply ? t("card.editReply") : t("card.replyLabel")}
                    </label>
                    <textarea
                      id={`reply-${review.id}`}
                      className="min-h-20 w-full rounded border border-border bg-bg px-3 py-2 text-sm"
                      value={drafts[review.id] ?? ""}
                      maxLength={4000}
                      onChange={(event) =>
                        setDrafts((current) => ({
                          ...current,
                          [review.id]: event.target.value,
                        }))
                      }
                    />
                    <Button
                      type="button"
                      className="min-h-11 w-full"
                      disabled={actingId === review.id || !(drafts[review.id] ?? "").trim()}
                      loading={actingId === review.id}
                      loadingLabel={t("actions.submitting")}
                      onClick={() => void submitReply(review.id)}
                    >
                      {actingId === review.id
                        ? t("actions.submitting")
                        : hasReply
                          ? t("actions.update")
                          : t("actions.submit")}
                    </Button>
                  </div>
                ) : review.vendor_reply ? (
                  <div className="rounded bg-bg-2 px-3 py-2 text-sm text-text-2">
                    <p className="font-medium text-display-ink">{t("card.yourReply")}</p>
                    <p>{review.vendor_reply}</p>
                  </div>
                ) : null}
              </li>
            );
          })}
        </ul>
      )}
    </div>
  );
}
