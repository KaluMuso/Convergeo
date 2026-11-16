"use client";

import { useSession } from "@vergeo/auth/use-session";
import { ApiError } from "@vergeo/config";
import { useTranslations } from "next-intl";
import { useCallback, useMemo } from "react";

import { Badge } from "../../../listings/new/_lib/ui";
import {
  createCollabClient,
  type CollabClient,
  type CollabStatusName,
} from "../_lib/collab-client";
import { sectionForField, type FieldError } from "../_lib/collab-readiness";

export function useCollabClient(): {
  client: CollabClient;
  hasSession: boolean;
  sessionLoading: boolean;
} {
  const { session, loading } = useSession();
  const getToken = useCallback(
    () => session?.access_token ?? null,
    [session?.access_token],
  );
  const client = useMemo(() => createCollabClient(getToken), [getToken]);
  return { client, hasSession: Boolean(session), sessionLoading: loading };
}

const STATUS_VARIANT: Record<
  CollabStatusName,
  "new" | "free" | "sold_out" | "public" | "promotion"
> = {
  draft: "new",
  submitted: "public",
  changes_requested: "promotion",
  approved: "free",
  declined: "sold_out",
  published: "free",
};

export function CollabStatusBadge({ status }: { status: CollabStatusName }) {
  const t = useTranslations("vendor");
  return (
    <Badge
      variant={STATUS_VARIANT[status]}
      label={t(`events.collab.status.${status}`)}
    />
  );
}

/** Readiness percentage with an accessible progress bar. */
export function ReadinessMeter({ pct }: { pct: number }) {
  const t = useTranslations("vendor");
  const safe = Math.max(0, Math.min(100, Math.round(pct)));
  return (
    <div className="flex flex-col gap-1" data-testid="readiness-meter">
      <div className="flex items-baseline justify-between text-sm">
        <span className="font-medium text-text">
          {t("events.collab.readiness.label")}
        </span>
        <span className="font-semibold text-text" data-testid="readiness-pct">
          {t("events.collab.readiness.value", { pct: safe })}
        </span>
      </div>
      <div
        role="progressbar"
        aria-valuemin={0}
        aria-valuemax={100}
        aria-valuenow={safe}
        aria-label={t("events.collab.readiness.label")}
        className="h-2 w-full overflow-hidden rounded-full bg-bg-2"
      >
        <div className="h-full bg-primary" style={{ width: `${safe}%` }} />
      </div>
    </div>
  );
}

/** Translates an ApiError (or anything) into a vendor.events.collab.errors message. */
export function useCollabErrorText() {
  const t = useTranslations("vendor");
  return useCallback(
    (error: unknown): string => {
      if (error instanceof ApiError) {
        const known: Record<string, string> = {
          checklist_incomplete: "checklistIncomplete",
          forbidden: "forbidden",
          kyc_required: "kycRequired",
          invalid_transition: "invalidTransition",
          validation_error: "invalidInput",
          not_found: "notFound",
          conflict: "conflict",
          rate_limited: "rateLimited",
          feature_disabled: "disabled",
          organiser_unavailable: "organiserUnavailable",
          past_instance: "pastStart",
          organiser_dispute_suspended: "disputeSuspended",
          event_high_value_verification_required: "highValue",
        };
        const key = known[error.code];
        if (key) {
          return t(`events.collab.errors.${key}`);
        }
      }
      return t("events.collab.errors.generic");
    },
    [t],
  );
}

export function fieldErrorsFromApi(error: unknown): FieldError[] {
  if (error instanceof ApiError && Array.isArray(error.details?.fields)) {
    return (error.details.fields as Array<Record<string, unknown>>)
      .filter((f) => typeof f.field === "string" && typeof f.code === "string")
      .map((f) => ({ field: String(f.field), code: String(f.code) }));
  }
  return [];
}

export function FieldErrorList({ errors }: { errors: FieldError[] }) {
  const t = useTranslations("vendor");
  if (errors.length === 0) {
    return null;
  }
  return (
    <div
      role="alert"
      className="rounded-lg border border-danger p-3"
      data-testid="collab-field-errors"
    >
      <p className="text-sm font-medium text-danger">
        {t("events.collab.errors.checklistIncomplete")}
      </p>
      <ul className="mt-1 list-disc pl-5 text-sm text-danger">
        {errors.map((error) => (
          <li key={`${error.field}:${error.code}`}>
            {t(`events.collab.sections.${sectionForField(error.field)}`)}:{" "}
            {t(`events.collab.fieldErrors.${error.code}`)}
          </li>
        ))}
      </ul>
    </div>
  );
}
