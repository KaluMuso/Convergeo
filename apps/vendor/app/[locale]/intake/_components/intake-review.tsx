"use client";

import { useSession } from "@vergeo/auth/use-session";
import { formatK } from "@vergeo/i18n";
import Link from "next/link";
import { useTranslations } from "next-intl";
import { useCallback, useEffect, useMemo, useState } from "react";

import { VendorErrorState } from "../../_components/async-state";
import { zmwDecimalToNgwee } from "../../listings/new/_lib/money";
import {
  createIntakeClient,
  type DraftPatch,
  type IntakeSessionDetail,
} from "../_lib/intake-client";
import { Button, FormField, Input, Select, Spinner } from "../_lib/ui";

type IntakeReviewProps = {
  locale: string;
  sessionId: string;
};

/** ngwee -> the editable decimal string, without float arithmetic. */
function ngweeToDecimal(ngwee: number | null): string {
  if (ngwee === null) return "";
  const sign = ngwee < 0 ? "-" : "";
  const absolute = Math.abs(ngwee);
  const major = Math.floor(absolute / 100);
  const minor = absolute % 100;
  return `${sign}${major}.${String(minor).padStart(2, "0")}`;
}

export function IntakeReview({ locale, sessionId }: IntakeReviewProps) {
  const t = useTranslations("vendor");
  const { session, loading: sessionLoading } = useSession();
  const [detail, setDetail] = useState<IntakeSessionDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [loadFailed, setLoadFailed] = useState(false);
  const [reloadKey, setReloadKey] = useState(0);

  const [title, setTitle] = useState("");
  const [price, setPrice] = useState("");
  const [condition, setCondition] = useState("");
  const [description, setDescription] = useState("");

  const [saving, setSaving] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [actionErrorKey, setActionErrorKey] = useState<string | null>(null);
  const [submitted, setSubmitted] = useState(false);

  const getToken = useCallback(() => session?.access_token ?? null, [session?.access_token]);
  const intakeClient = useMemo(() => createIntakeClient(getToken), [getToken]);

  const hydrate = useCallback((next: IntakeSessionDetail) => {
    setDetail(next);
    setTitle(next.draft.title ?? "");
    setPrice(ngweeToDecimal(next.draft.price_ngwee));
    setCondition(next.draft.condition ?? "");
    setDescription(next.draft.description ?? "");
  }, []);

  useEffect(() => {
    if (sessionLoading) return;
    if (!session) {
      setLoading(false);
      return;
    }
    let cancelled = false;
    setLoading(true);
    setLoadFailed(false);
    intakeClient
      .getSession(sessionId)
      .then((next) => {
        if (!cancelled) hydrate(next);
      })
      .catch(() => {
        if (!cancelled) setLoadFailed(true);
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [hydrate, intakeClient, reloadKey, session, sessionId, sessionLoading]);

  const provenanceFor = useCallback(
    (field: string) => detail?.provenance.find((entry) => entry.field_name === field) ?? null,
    [detail],
  );

  const handleSave = async () => {
    if (!detail) return;
    setSaving(true);
    setActionErrorKey(null);
    try {
      const patch: DraftPatch = {
        title: title.trim() === "" ? null : title.trim(),
        condition: condition === "" ? null : condition,
        description: description.trim() === "" ? null : description.trim(),
      };
      if (price.trim() === "") {
        patch.price_ngwee = null;
      } else {
        // Parsed as an exact integer; a bad value fails here, never silently.
        patch.price_ngwee = zmwDecimalToNgwee(price);
      }
      hydrate(await intakeClient.patchDraft(sessionId, patch));
    } catch {
      setActionErrorKey("intake.errors.saveFailed");
    } finally {
      setSaving(false);
    }
  };

  const handleSubmit = async () => {
    setSubmitting(true);
    setActionErrorKey(null);
    try {
      await intakeClient.submit(sessionId);
      setSubmitted(true);
      setReloadKey((key) => key + 1);
    } catch {
      setActionErrorKey("intake.errors.submitFailed");
    } finally {
      setSubmitting(false);
    }
  };

  if (loading || sessionLoading) {
    return (
      <div className="flex min-h-[40vh] items-center justify-center">
        <Spinner label={t("intake.loading")} />
      </div>
    );
  }

  if (loadFailed || !detail) {
    return (
      <VendorErrorState
        title={t("intake.errors.loadFailed")}
        retryLabel={t("intake.error.retry")}
        onRetry={() => setReloadKey((key) => key + 1)}
        data-testid="intake-review-error"
      />
    );
  }

  return (
    <section className="flex flex-col gap-5 p-4" data-testid="intake-review">
      <header className="flex flex-col gap-1">
        <Link href={`/${locale}/intake`} className="text-sm underline">
          {t("intake.detail.back")}
        </Link>
        <h1 className="text-xl font-semibold">{t("intake.detail.title")}</h1>
        <p className="text-sm text-muted-foreground">{t("intake.detail.intro")}</p>
      </header>

      {/* Follow-ups recorded on the record — the lane never messages the vendor. */}
      {detail.pending_requests.length > 0 ? (
        <ul className="flex flex-col gap-2 rounded-lg border border-border p-3">
          {detail.pending_requests.map((request) => (
            <li key={`${request.key}-${request.field_name ?? ""}`} className="text-sm">
              {t(`intake.question.${request.key.replace(/^intake\.question\./, "")}`)}
            </li>
          ))}
        </ul>
      ) : null}

      <section className="flex flex-col gap-2">
        <h2 className="text-base font-medium">{t("intake.detail.photos")}</h2>
        {detail.media.length === 0 ? (
          <p className="text-sm text-muted-foreground">{t("intake.detail.noPhotos")}</p>
        ) : (
          <ul className="flex flex-wrap gap-2">
            {detail.media.map((item, index) =>
              item.signed_url ? (
                <li key={item.id}>
                  {/* Short-lived signed URL over a private bucket — deliberately not
                      next/image, which would proxy and cache a quarantined asset. */}
                  <img
                    src={item.signed_url}
                    alt={t("intake.detail.photoAlt", { position: index + 1 })}
                    className="h-24 w-24 rounded object-cover"
                    loading="lazy"
                  />
                </li>
              ) : null,
            )}
          </ul>
        )}
      </section>

      <form
        className="flex flex-col gap-4"
        onSubmit={(event) => {
          event.preventDefault();
          void handleSave();
        }}
      >
        <FormField id="intake-title" label={t("intake.fields.title")}>
          <Input value={title} onChange={(event) => setTitle(event.target.value)} />
        </FormField>
        <p className="text-xs text-muted-foreground">
          {t("intake.source.label")}:{" "}
          {t(`intake.source.${provenanceFor("title")?.source ?? "vendor_typed"}`)}
        </p>

        <FormField id="intake-price" label={t("intake.fields.price_ngwee")}>
          <Input
            inputMode="decimal"
            value={price}
            onChange={(event) => setPrice(event.target.value)}
          />
        </FormField>
        <p className="text-xs text-muted-foreground">
          {t("intake.source.label")}:{" "}
          {t(`intake.source.${provenanceFor("price_ngwee")?.source ?? "vendor_typed"}`)}
          {detail.draft.price_ngwee === null ? "" : ` · ${formatK(detail.draft.price_ngwee)}`}
        </p>

        <FormField id="intake-condition" label={t("intake.fields.condition")}>
          <Select value={condition} onChange={(event) => setCondition(event.target.value)}>
            <option value="">—</option>
            <option value="new">{t("listings.fields.conditionNew")}</option>
            <option value="refurbished">{t("listings.fields.conditionRefurbished")}</option>
          </Select>
        </FormField>

        <FormField id="intake-description" label={t("intake.fields.description")}>
          <Input value={description} onChange={(event) => setDescription(event.target.value)} />
        </FormField>

        <Button
          type="submit"
          disabled={saving}
          loading={saving}
          loadingLabel={t("intake.detail.saving")}
        >
          {t("intake.detail.save")}
        </Button>
      </form>

      {detail.missing_fields.length > 0 ? (
        <section className="flex flex-col gap-1">
          <h2 className="text-base font-medium">{t("intake.detail.missing")}</h2>
          <ul className="list-disc pl-5 text-sm">
            {detail.missing_fields.map((field) => (
              <li key={field}>{t(`intake.fields.${field}`)}</li>
            ))}
          </ul>
        </section>
      ) : null}

      {actionErrorKey ? (
        <p role="alert" className="text-sm text-danger">
          {t(actionErrorKey)}
        </p>
      ) : null}

      {submitted ? (
        <p role="status" className="text-sm">
          {t("intake.detail.submitted")}
        </p>
      ) : (
        <Button
          type="button"
          onClick={() => void handleSubmit()}
          disabled={!detail.submittable || submitting}
          loading={submitting}
          loadingLabel={t("intake.detail.submitting")}
          data-testid="intake-submit"
        >
          {t("intake.detail.submit")}
        </Button>
      )}
    </section>
  );
}
