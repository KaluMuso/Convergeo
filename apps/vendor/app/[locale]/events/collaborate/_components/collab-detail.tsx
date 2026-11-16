"use client";

import { formatK } from "@vergeo/i18n";
import Link from "next/link";
import { useTranslations } from "next-intl";
import { useCallback, useEffect, useState } from "react";

import {
  Button,
  FormField,
  Spinner,
  Textarea,
} from "../../../listings/new/_lib/ui";
import { type CollabRequest } from "../_lib/collab-client";
import {
  bpsToPercent,
  normaliseChecklist,
  normaliseDraft,
  readinessItems,
  type ReadinessKey,
} from "../_lib/collab-readiness";

import { CollabForm } from "./collab-form";
import {
  CollabStatusBadge,
  FieldErrorList,
  ReadinessMeter,
  fieldErrorsFromApi,
  useCollabClient,
  useCollabErrorText,
} from "./collab-parts";

type Props = { locale: string; requestId: string };

const ITEM_LABEL: Record<ReadinessKey, string> = {
  venue: "venue",
  schedule: "schedule",
  capacity: "capacity",
  equipment_sound: "equipment.items.sound",
  equipment_stage: "equipment.items.stage",
  equipment_power: "equipment.items.power",
  equipment_seating: "equipment.items.seating",
  equipment_security: "equipment.items.security",
  permits: "permits",
  tiers: "tiers",
  revenue_share: "share",
};

export function CollabDetail({ locale, requestId }: Props) {
  const t = useTranslations("vendor");
  const { client, hasSession, sessionLoading } = useCollabClient();
  const errorText = useCollabErrorText();
  const [request, setRequest] = useState<CollabRequest | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [fieldErrors, setFieldErrors] = useState<
    ReturnType<typeof fieldErrorsFromApi>
  >([]);
  const [busy, setBusy] = useState<string | null>(null);
  const [reasonMode, setReasonMode] = useState<"decline" | "changes" | null>(
    null,
  );
  const [reason, setReason] = useState("");

  useEffect(() => {
    if (sessionLoading) return;
    if (!hasSession) {
      setLoading(false);
      return;
    }
    let cancelled = false;
    client
      .getRequest(requestId)
      .then((row) => {
        if (!cancelled) setRequest(row);
      })
      .catch((caught: unknown) => {
        if (!cancelled) setError(errorText(caught));
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [client, hasSession, sessionLoading, requestId, errorText]);

  const run = useCallback(
    async (name: string, action: () => Promise<CollabRequest>) => {
      setBusy(name);
      setError(null);
      setFieldErrors([]);
      try {
        setRequest(await action());
        setReasonMode(null);
        setReason("");
      } catch (caught) {
        setFieldErrors(fieldErrorsFromApi(caught));
        setError(errorText(caught));
      } finally {
        setBusy(null);
      }
    },
    [errorText],
  );

  if (sessionLoading || loading) {
    return (
      <div className="flex min-h-[40vh] items-center justify-center">
        <Spinner label={t("events.collab.loading")} />
      </div>
    );
  }
  if (!request) {
    return (
      <p role="alert" className="text-sm text-danger">
        {error ?? t("events.collab.errors.notFound")}
      </p>
    );
  }

  const isOrganiser = request.my_role === "organiser";
  const isProposer = !isOrganiser;
  const editable =
    isProposer &&
    (request.status === "draft" || request.status === "changes_requested");

  if (editable) {
    return (
      <div className="flex flex-col gap-4">
        {request.status === "changes_requested" && request.organiser_note ? (
          <div
            className="rounded-lg border border-border bg-surface p-3"
            data-testid="collab-organiser-note"
          >
            <p className="text-sm font-semibold text-text">
              {t("events.collab.detail.changesAsked")}
            </p>
            <p className="text-sm text-text-2">{request.organiser_note}</p>
          </div>
        ) : null}
        <CollabForm locale={locale} request={request} onSaved={setRequest} />
      </div>
    );
  }

  const draft = normaliseDraft(request.event_draft);
  const checklist = normaliseChecklist(request.checklist);
  const items = readinessItems(checklist, request.revenue_share_bps);
  const other = isOrganiser ? request.proposer : request.organiser;

  return (
    <div className="flex flex-col gap-4" data-testid="collab-detail">
      <header className="flex flex-col gap-2">
        <div className="flex items-start justify-between gap-2">
          <h1 className="text-xl font-semibold text-text">
            {draft.title ?? t("events.collab.untitled")}
          </h1>
          <CollabStatusBadge status={request.status} />
        </div>
        <p className="text-sm text-text-2">
          {isOrganiser
            ? t("events.collab.list.from", { name: other.display_name })
            : t("events.collab.list.to", { name: other.display_name })}
        </p>
        <ReadinessMeter pct={request.readiness_pct} />
      </header>

      {request.organiser_note && request.status === "declined" ? (
        <div
          className="rounded-lg border border-border bg-surface p-3"
          data-testid="collab-organiser-note"
        >
          <p className="text-sm font-semibold text-text">
            {t("events.collab.detail.declinedReason")}
          </p>
          <p className="text-sm text-text-2">{request.organiser_note}</p>
        </div>
      ) : null}

      <section className="flex flex-col gap-2 rounded-xl border border-border bg-surface p-4">
        <h2 className="text-sm font-semibold uppercase tracking-wide text-text-3">
          {t("events.collab.detail.summary")}
        </h2>
        <dl className="grid grid-cols-[auto_1fr] gap-x-3 gap-y-1 text-sm">
          <dt className="text-text-2">{t("events.collab.sections.venue")}</dt>
          <dd>
            {[checklist.venue.name, checklist.venue.landmark]
              .filter(Boolean)
              .join(" · ") || "-"}
            {checklist.venue.lat !== null && checklist.venue.lng !== null
              ? ` (${checklist.venue.lat}, ${checklist.venue.lng})`
              : ""}
          </dd>
          <dt className="text-text-2">
            {t("events.collab.sections.schedule")}
          </dt>
          <dd>
            {checklist.schedule.starts_at
              ? new Date(checklist.schedule.starts_at).toLocaleString(locale)
              : "-"}
          </dd>
          <dt className="text-text-2">
            {t("events.collab.sections.capacity")}
          </dt>
          <dd>{checklist.capacity.capacity ?? "-"}</dd>
          <dt className="text-text-2">{t("events.collab.sections.tiers")}</dt>
          <dd>
            {checklist.tiers.length === 0
              ? "-"
              : checklist.tiers
                  .map((tier) => `${tier.name} (${formatK(tier.price_ngwee)})`)
                  .join(", ")}
          </dd>
          <dt className="text-text-2">{t("events.collab.sections.share")}</dt>
          <dd data-testid="collab-detail-share">
            {request.revenue_share_bps === null
              ? "-"
              : t("events.collab.checklist.share.preview", {
                  cohost: bpsToPercent(request.revenue_share_bps),
                  organiser: bpsToPercent(10_000 - request.revenue_share_bps),
                })}
          </dd>
        </dl>
        <ul
          className="mt-2 grid grid-cols-1 gap-1 text-sm"
          data-testid="collab-item-list"
        >
          {(Object.keys(items) as ReadinessKey[]).map((key) => (
            <li key={key} className="flex items-center gap-2">
              <span aria-hidden="true">{items[key] ? "✓" : "○"}</span>
              <span className={items[key] ? "text-text" : "text-text-2"}>
                {t(
                  key === "venue" ||
                    key === "schedule" ||
                    key === "capacity" ||
                    key === "permits" ||
                    key === "tiers" ||
                    key === "revenue_share"
                    ? `events.collab.sections.${ITEM_LABEL[key]}`
                    : `events.collab.checklist.${ITEM_LABEL[key]}`,
                )}
              </span>
              <span className="sr-only">
                {items[key]
                  ? t("events.collab.detail.done")
                  : t("events.collab.detail.open")}
              </span>
            </li>
          ))}
        </ul>
      </section>

      <p className="text-sm text-text-2">
        {t("events.collab.detail.accountability")}
      </p>

      <FieldErrorList errors={fieldErrors} />
      {error ? (
        <p
          role="alert"
          className="text-sm text-danger"
          data-testid="collab-error"
        >
          {error}
        </p>
      ) : null}

      {isOrganiser && request.status === "submitted" ? (
        <div className="flex flex-col gap-2">
          {reasonMode ? (
            <div className="flex flex-col gap-2 rounded-lg border border-border p-3">
              <FormField label={t("events.collab.detail.reasonLabel")}>
                <Textarea
                  value={reason}
                  maxLength={1000}
                  onChange={(e) => setReason(e.target.value)}
                  data-testid="collab-reason"
                />
              </FormField>
              <Button
                type="button"
                variant={reasonMode === "decline" ? "destructive" : "primary"}
                loading={busy === reasonMode}
                loadingLabel={t("events.collab.form.saving")}
                disabled={reason.trim().length < 3 || busy !== null}
                data-testid="collab-confirm-reason"
                onClick={() =>
                  void run(reasonMode, () =>
                    reasonMode === "decline"
                      ? client.decline(request.id, reason.trim())
                      : client.requestChanges(request.id, reason.trim()),
                  )
                }
              >
                {reasonMode === "decline"
                  ? t("events.collab.detail.decline")
                  : t("events.collab.detail.askChanges")}
              </Button>
              <Button
                type="button"
                variant="ghost"
                loadingLabel={t("events.collab.loading")}
                onClick={() => setReasonMode(null)}
              >
                {t("events.collab.detail.cancel")}
              </Button>
            </div>
          ) : (
            <>
              <Button
                type="button"
                loading={busy === "approve"}
                loadingLabel={t("events.collab.form.saving")}
                disabled={busy !== null}
                data-testid="collab-approve"
                onClick={() =>
                  void run("approve", () => client.approve(request.id))
                }
              >
                {t("events.collab.detail.approve")}
              </Button>
              <Button
                type="button"
                variant="secondary"
                loadingLabel={t("events.collab.loading")}
                data-testid="collab-ask-changes"
                onClick={() => setReasonMode("changes")}
              >
                {t("events.collab.detail.askChanges")}
              </Button>
              <Button
                type="button"
                variant="secondary"
                loadingLabel={t("events.collab.loading")}
                data-testid="collab-decline"
                onClick={() => setReasonMode("decline")}
              >
                {t("events.collab.detail.decline")}
              </Button>
            </>
          )}
        </div>
      ) : null}

      {isOrganiser && request.status === "approved" ? (
        <Button
          type="button"
          loading={busy === "publish"}
          loadingLabel={t("events.collab.form.saving")}
          disabled={busy !== null}
          data-testid="collab-publish"
          onClick={() => void run("publish", () => client.publish(request.id))}
        >
          {t("events.collab.detail.publish")}
        </Button>
      ) : null}

      {isProposer && request.status === "submitted" ? (
        <p className="text-sm text-text-2">
          {t("events.collab.detail.waiting")}
        </p>
      ) : null}
      {isProposer && request.status === "approved" ? (
        <p className="text-sm text-text-2">
          {t("events.collab.detail.approvedWaiting")}
        </p>
      ) : null}
      {request.status === "published" ? (
        <p className="text-sm text-text" data-testid="collab-published">
          {isOrganiser ? (
            request.event_id ? (
              <Link
                className="font-medium text-primary underline"
                href={`/${locale}/events/${request.event_id}/edit`}
              >
                {t("events.collab.detail.openEvent")}
              </Link>
            ) : null
          ) : (
            t("events.collab.detail.publishedCoHost", {
              name: request.organiser.display_name,
            })
          )}
        </p>
      ) : null}

      <section className="flex flex-col gap-2">
        <h2 className="text-sm font-semibold uppercase tracking-wide text-text-3">
          {t("events.collab.detail.history")}
        </h2>
        <ol
          className="flex flex-col gap-1 text-sm text-text-2"
          data-testid="collab-history"
        >
          {request.audit.map((entry, index) => (
            <li key={`${entry.created_at}-${index}`}>
              {t(`events.collab.audit.${entry.action}`)}
              {entry.reason ? ` — ${entry.reason}` : ""}
            </li>
          ))}
        </ol>
      </section>

      <Link
        href={`/${locale}/events/${isOrganiser ? "requests" : "collaborate"}`}
        className="inline-flex min-h-11 items-center text-sm font-medium text-primary underline"
      >
        {t("events.collab.detail.back")}
      </Link>
    </div>
  );
}
