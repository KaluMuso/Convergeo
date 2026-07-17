"use client";

import { useSession } from "@vergeo/auth/use-session";
import { ApiError, createApiClient } from "@vergeo/config";
import { Button } from "@vergeo/ui/src/button";
import { FormField } from "@vergeo/ui/src/form-field";
import { StarRating } from "@vergeo/ui/src/star-rating";
import { Textarea } from "@vergeo/ui/src/textarea";
import { useTranslations } from "next-intl";
import { useCallback, useEffect, useMemo, useState } from "react";

type ServiceReviewData = {
  id: string;
  rating: number;
  body: string | null;
  vendor_reply: string | null;
  created_at: string;
};

type Eligibility = {
  job_id: string;
  can_review: boolean;
  completed: boolean;
  review: ServiceReviewData | null;
};

function getApiBaseUrl(): string {
  return process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";
}

/**
 * Post-completion review prompt on the customer's job page. Fetches eligibility
 * (the API gates on a completed service order owned by the caller) and shows the
 * submitted review or an editable form. Renders nothing until the job is done.
 */
export function ServiceReviewForm({ jobId }: { jobId: string }) {
  const t = useTranslations("services.reviews");
  const { session, loading: sessionLoading } = useSession();

  const getToken = useCallback(() => session?.access_token ?? null, [session?.access_token]);
  const client = useMemo(() => createApiClient({ baseUrl: getApiBaseUrl(), getToken }), [getToken]);

  const [eligibility, setEligibility] = useState<Eligibility | null>(null);
  const [loading, setLoading] = useState(true);
  const [rating, setRating] = useState(0);
  const [body, setBody] = useState("");
  const [editing, setEditing] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [submitted, setSubmitted] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const data = await client.request<Eligibility>(`/service-reviews/eligibility/${jobId}`);
      setEligibility(data);
      if (data.review) {
        setRating(data.review.rating);
        setBody(data.review.body ?? "");
      }
      setError(null);
    } catch (err) {
      // Not the job owner (403) or unknown job (404) — hide the widget entirely.
      if (err instanceof ApiError && (err.status === 403 || err.status === 404)) {
        setEligibility(null);
      } else {
        setError(t("errors.loadFailed"));
      }
    } finally {
      setLoading(false);
    }
  }, [client, jobId, t]);

  useEffect(() => {
    if (sessionLoading || !jobId) {
      return;
    }
    if (!session) {
      setLoading(false);
      return;
    }
    void load();
  }, [jobId, load, session, sessionLoading]);

  const submit = useCallback(async () => {
    if (rating < 1) {
      return;
    }
    setSubmitting(true);
    setError(null);
    try {
      await client.request("/service-reviews", {
        method: "POST",
        body: JSON.stringify({ job_id: jobId, rating, body: body.trim() || null }),
      });
      setSubmitted(true);
      setEditing(false);
      await load();
    } catch (err) {
      if (err instanceof ApiError && err.status === 429) {
        setError(t("errors.rateLimited"));
      } else {
        setError(t("errors.generic"));
      }
    } finally {
      setSubmitting(false);
    }
  }, [body, client, jobId, load, rating, t]);

  if (sessionLoading || loading) {
    return null;
  }
  if (!session || !eligibility || !eligibility.completed) {
    return null;
  }

  const existing = eligibility.review;
  const showForm = editing || (!existing && eligibility.can_review);
  const bodyFieldId = `service-review-body-${jobId}`;

  return (
    <section className="space-y-3 rounded border border-border bg-surface p-4">
      <header className="space-y-1">
        <h3 className="font-display text-h3 text-display-ink">{t("form.title")}</h3>
        <p className="text-sm text-text-2">{t("form.intro")}</p>
      </header>

      {error ? <p className="text-sm text-danger">{error}</p> : null}

      {existing && !editing ? (
        <div className="space-y-2">
          <p className="text-xs font-semibold uppercase tracking-wide text-text-3">
            {t("form.yourReview")}
          </p>
          <span role="img" aria-label={t("starsAria", { rating: existing.rating })}>
            <StarRating mode="display" value={existing.rating} />
          </span>
          {existing.body ? <p className="text-sm text-display-ink">{existing.body}</p> : null}
          {submitted ? <p className="text-sm text-primary">{t("form.submitted")}</p> : null}
          {eligibility.can_review ? (
            <Button
              type="button"
              variant="secondary"
              loadingLabel={t("form.edit")}
              onClick={() => setEditing(true)}
            >
              {t("form.edit")}
            </Button>
          ) : null}
        </div>
      ) : showForm ? (
        <div className="space-y-3">
          <div className="space-y-1">
            <span className="block text-sm font-medium text-text">{t("form.ratingLabel")}</span>
            <StarRating
              mode="input"
              value={rating}
              onChange={setRating}
              name={`service-review-rating-${jobId}`}
              inputAriaLabel={t("form.ratingAria")}
            />
          </div>
          <FormField id={bodyFieldId} label={t("form.bodyLabel")}>
            <Textarea
              value={body}
              onChange={(event) => setBody(event.target.value)}
              placeholder={t("form.bodyPlaceholder")}
              maxLength={4000}
            />
          </FormField>
          <Button
            type="button"
            loading={submitting}
            loadingLabel={t("form.submitting")}
            disabled={submitting || rating < 1}
            onClick={() => void submit()}
          >
            {t("form.submit")}
          </Button>
        </div>
      ) : null}
    </section>
  );
}
