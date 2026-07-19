"use client";

import { useSession } from "@vergeo/auth/use-session";
import { createApiClient } from "@vergeo/config";
import { Button } from "@vergeo/ui/src/button";
import { FormField } from "@vergeo/ui/src/form-field";
import { Input } from "@vergeo/ui/src/input";
import { Textarea } from "@vergeo/ui/src/textarea";
import Link from "next/link";
import { useTranslations } from "next-intl";
import { useCallback, useEffect, useMemo, useState, type FormEvent } from "react";

import { getApiBaseUrl } from "../../../../../lib/api-base-url";

const SERVICE_CATEGORIES = [
  "beauty",
  "food_catering",
  "auto",
  "printing_creative",
  "home_services",
  "tech_services",
  "cleaning",
  "tailoring",
] as const;

const BUDGET_BANDS = ["under_500", "500_2000", "2000_5000", "over_5000", "flexible"] as const;

type ServiceCategory = (typeof SERVICE_CATEGORIES)[number];
type BudgetBand = (typeof BUDGET_BANDS)[number];

type DraftJob = {
  category: ServiceCategory;
  description: string;
  service_area: string;
  preferred_date: string;
  budget_band: BudgetBand;
};

type JobBroadcastSummary = {
  matched_count: number;
  notified_count: number;
  capped: boolean;
  no_match: boolean;
  admin_flagged: boolean;
  message_key: string;
};

type CreateJobResponse = {
  job: {
    id: string;
    broadcast?: JobBroadcastSummary | null;
  };
};

type PostJobFormProps = {
  locale: string;
  /** Category to preselect, e.g. forwarded from a service page's "Request quote" link. */
  initialCategory?: string;
};

const DRAFT_STORAGE_KEY = "vergeo5:post-job-draft";

function readDraft(): Partial<DraftJob> | null {
  if (typeof window === "undefined") {
    return null;
  }
  try {
    const raw = window.localStorage.getItem(DRAFT_STORAGE_KEY);
    if (!raw) {
      return null;
    }
    return JSON.parse(raw) as Partial<DraftJob>;
  } catch {
    return null;
  }
}

function writeDraft(draft: DraftJob): void {
  window.localStorage.setItem(DRAFT_STORAGE_KEY, JSON.stringify(draft));
}

function clearDraft(): void {
  window.localStorage.removeItem(DRAFT_STORAGE_KEY);
}

/**
 * Map a service-listing vertical (hyphenated, e.g. "food-catering") to a job
 * category (underscored, e.g. "food_catering"), returning undefined when it is
 * not a recognised category. Reconciles the two taxonomies so a "Request quote"
 * link from a service page preselects the right category instead of silently
 * defaulting (or being rejected by the API if it were forwarded verbatim).
 */
function normalizeServiceCategory(value: string | undefined): ServiceCategory | undefined {
  if (!value) {
    return undefined;
  }
  const underscored = value.replace(/-/g, "_");
  return (SERVICE_CATEGORIES as readonly string[]).includes(underscored)
    ? (underscored as ServiceCategory)
    : undefined;
}

export function PostJobForm({ locale, initialCategory }: PostJobFormProps) {
  const t = useTranslations("services");
  const { session, loading: sessionLoading } = useSession();
  const draft = useMemo(() => readDraft(), []);

  const [category, setCategory] = useState<ServiceCategory>(
    normalizeServiceCategory(initialCategory) ??
      (draft?.category as ServiceCategory) ??
      "home_services",
  );
  const [description, setDescription] = useState(draft?.description ?? "");
  const [serviceArea, setServiceArea] = useState(draft?.service_area ?? "");
  const [preferredDate, setPreferredDate] = useState(draft?.preferred_date ?? "");
  const [budgetBand, setBudgetBand] = useState<BudgetBand>(
    (draft?.budget_band as BudgetBand) ?? "flexible",
  );
  const [submitting, setSubmitting] = useState(false);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [successMessage, setSuccessMessage] = useState<string | null>(null);

  const persistDraft = useCallback(() => {
    writeDraft({
      category,
      description,
      service_area: serviceArea,
      preferred_date: preferredDate,
      budget_band: budgetBand,
    });
  }, [budgetBand, category, description, preferredDate, serviceArea]);

  useEffect(() => {
    if (!session?.access_token) {
      persistDraft();
    }
  }, [persistDraft, session?.access_token]);

  const handleSubmit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setErrorMessage(null);
    setSuccessMessage(null);

    if (!description.trim() || !serviceArea.trim()) {
      setErrorMessage(t("postJob.errors.required"));
      return;
    }

    if (!session?.access_token) {
      persistDraft();
      setErrorMessage(t("postJob.authRequired"));
      return;
    }

    setSubmitting(true);
    try {
      const client = createApiClient({
        baseUrl: getApiBaseUrl(),
        getToken: () => session.access_token,
      });
      const response = await client.request<CreateJobResponse>("/jobs", {
        method: "POST",
        body: JSON.stringify({
          category,
          description: description.trim(),
          service_area: serviceArea.trim(),
          preferred_date: preferredDate || null,
          budget_band: budgetBand,
          photo_paths: [],
        }),
      });
      clearDraft();
      const broadcast = response.job.broadcast;
      if (broadcast?.no_match) {
        setSuccessMessage(t("postJob.ack.noMatch"));
      } else {
        setSuccessMessage(t("postJob.ack.sent"));
      }
    } catch {
      setErrorMessage(t("postJob.errors.generic"));
    } finally {
      setSubmitting(false);
    }
  };

  if (sessionLoading) {
    return (
      <p className="font-body text-sm text-text-3" aria-live="polite">
        {t("postJob.submitting")}
      </p>
    );
  }

  return (
    <form className="mx-auto flex w-full max-w-[360px] flex-col gap-4" onSubmit={handleSubmit}>
      <header className="space-y-1">
        <h1 className="font-display text-h1 text-display-ink">{t("postJob.title")}</h1>
        <p className="font-body text-sm text-text-2">{t("postJob.subtitle")}</p>
      </header>

      {!session?.access_token ? (
        <div className="rounded-lg border border-border bg-bg-2 p-3">
          <p className="font-body text-sm text-text-2">{t("postJob.draftSaved")}</p>
          <Link
            href={`/${locale}/login?next=/${locale}/services/post-job`}
            className="mt-2 inline-flex min-h-11 items-center font-body text-sm font-medium text-primary underline underline-offset-2"
          >
            {t("postJob.authCta")}
          </Link>
        </div>
      ) : null}

      <FormField id="post-job-category" label={t("postJob.category.label")}>
        <select
          id="post-job-category"
          className="min-h-11 w-full rounded-md border border-border bg-surface px-3 font-body text-sm text-text"
          value={category}
          onChange={(event) => setCategory(event.target.value as ServiceCategory)}
          required
        >
          {SERVICE_CATEGORIES.map((value) => (
            <option key={value} value={value}>
              {t(`postJob.category.${value}`)}
            </option>
          ))}
        </select>
      </FormField>

      <FormField id="post-job-description" label={t("postJob.description.label")}>
        <Textarea
          id="post-job-description"
          value={description}
          onChange={(event) => setDescription(event.target.value)}
          placeholder={t("postJob.description.placeholder")}
          rows={4}
          required
          minLength={10}
        />
      </FormField>

      <FormField id="post-job-area" label={t("postJob.serviceArea.label")}>
        <Input
          id="post-job-area"
          value={serviceArea}
          onChange={(event) => setServiceArea(event.target.value)}
          placeholder={t("postJob.serviceArea.placeholder")}
          required
        />
      </FormField>

      <FormField id="post-job-date" label={t("postJob.preferredDate.label")}>
        <Input
          id="post-job-date"
          type="date"
          value={preferredDate}
          onChange={(event) => setPreferredDate(event.target.value)}
        />
      </FormField>

      <FormField id="post-job-budget" label={t("postJob.budgetBand.label")}>
        <select
          id="post-job-budget"
          className="min-h-11 w-full rounded-md border border-border bg-surface px-3 font-body text-sm text-text"
          value={budgetBand}
          onChange={(event) => setBudgetBand(event.target.value as BudgetBand)}
          required
        >
          {BUDGET_BANDS.map((value) => (
            <option key={value} value={value}>
              {t(`postJob.budgetBand.${value}`)}
            </option>
          ))}
        </select>
      </FormField>

      <div className="space-y-1">
        <p className="font-body text-sm font-medium text-text">{t("postJob.photos.label")}</p>
        <p className="font-body text-xs text-text-3">{t("postJob.photos.help")}</p>
      </div>

      {errorMessage ? (
        <p className="font-body text-sm text-danger" role="alert">
          {errorMessage}
        </p>
      ) : null}
      {successMessage ? (
        <p className="font-body text-sm text-success" role="status">
          {successMessage}
        </p>
      ) : null}

      <Button
        type="submit"
        className="min-h-11 w-full"
        disabled={submitting}
        loading={submitting}
        loadingLabel={t("postJob.submitting")}
      >
        {submitting ? t("postJob.submitting") : t("postJob.submit")}
      </Button>
    </form>
  );
}
