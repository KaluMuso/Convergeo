"use client";

import { ApiError } from "@vergeo/config";
import { CloudinaryImage } from "@vergeo/ui/src/media/cloudinary-image";
import { useLocale, useTranslations } from "next-intl";
import { useCallback, useEffect, useState } from "react";

import { AdminLoadFailure } from "../../_components/AdminLoadFailure";
import { resolveQueueLoadFailure } from "../../_components/queue-load-failure";
import { EmptyBlock, LoadingBlock } from "../../_components/StateBlocks";

import {
  listEventSponsorQueue,
  reviewEventSponsor,
  type SponsorQueueItem,
  type SponsorView,
} from "./api";

const CUSTOMER_ORIGIN = process.env.NEXT_PUBLIC_VERGEO_CUSTOMER_URL ?? "http://localhost:3000";

type RejectTarget = {
  eventId: string;
  sponsor: SponsorView;
};

export function SponsorReviewBoard() {
  const t = useTranslations("admin.eventSponsors.queue");
  const locale = useLocale();
  const [items, setItems] = useState<SponsorQueueItem[] | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [permissionDenied, setPermissionDenied] = useState(false);
  const [statusMessage, setStatusMessage] = useState<string | null>(null);
  const [busyKey, setBusyKey] = useState<string | null>(null);
  const [rejectTarget, setRejectTarget] = useState<RejectTarget | null>(null);
  const [rejectNote, setRejectNote] = useState("");

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    setPermissionDenied(false);
    try {
      const page = await listEventSponsorQueue();
      setItems(page.items);
    } catch (err) {
      const failure = resolveQueueLoadFailure(err);
      setPermissionDenied(failure.permissionDenied);
      setError(t(failure.messageKey));
      setItems(null);
    } finally {
      setLoading(false);
    }
  }, [t]);

  useEffect(() => {
    void load();
  }, [load]);

  const submitDecision = useCallback(
    async (
      eventId: string,
      sponsor: SponsorView,
      decision: "approved" | "rejected",
      note?: string,
    ) => {
      const busy = `${eventId}:${sponsor.index}`;
      setBusyKey(busy);
      setError(null);
      setStatusMessage(null);
      try {
        await reviewEventSponsor(eventId, {
          index: sponsor.index,
          name: sponsor.name,
          decision,
          note: note?.trim() ? note.trim() : null,
        });
        setStatusMessage(t("decisionSaved"));
        setRejectTarget(null);
        setRejectNote("");
        await load();
      } catch (err: unknown) {
        if (err instanceof ApiError && err.status === 409) {
          setError(t("conflict"));
          await load();
        } else {
          setError(t("actionError"));
        }
      } finally {
        setBusyKey(null);
      }
    },
    [load, t],
  );

  if (loading) {
    return <LoadingBlock label={t("loading")} />;
  }

  if (error && items === null) {
    return (
      <AdminLoadFailure
        permissionDenied={permissionDenied}
        message={error}
        hint={permissionDenied ? t("permissionDenied") : undefined}
        retryLabel={t("retry")}
        onRetry={() => void load()}
      />
    );
  }

  const queue = items ?? [];

  return (
    <div className="space-y-4" data-testid="event-sponsor-review-board">
      {statusMessage ? (
        <p role="status" className="text-sm text-success">
          {statusMessage}
        </p>
      ) : null}
      {error ? (
        <p role="alert" className="text-sm text-danger">
          {error}
        </p>
      ) : null}
      {queue.length === 0 ? (
        <EmptyBlock title={t("empty")} body={t("emptyHint")} />
      ) : (
        <ul className="m-0 flex list-none flex-col gap-4 p-0">
          {queue.map((event) => (
            <li
              key={event.event_id}
              className="rounded-xl border border-border bg-surface p-4"
              data-testid={`sponsor-event-${event.event_id}`}
            >
              <div className="flex flex-col gap-1 sm:flex-row sm:items-start sm:justify-between">
                <div>
                  <h3 className="font-display text-lg text-text">{event.title}</h3>
                  {event.organiser_name ? (
                    <p className="text-sm text-muted">
                      {t("organiser", { name: event.organiser_name })}
                    </p>
                  ) : null}
                  <p className="text-sm text-muted">
                    {t("eventStatus", { status: event.event_status })}
                  </p>
                </div>
                <a
                  href={`${CUSTOMER_ORIGIN}/${locale}/e/${event.slug}`}
                  className="inline-flex min-h-11 items-center text-sm font-medium text-primary underline underline-offset-2"
                  target="_blank"
                  rel="noopener noreferrer"
                >
                  {t("viewEvent")}
                </a>
              </div>
              <ul className="mt-4 flex flex-col gap-3">
                {event.sponsors.map((sponsor) => {
                  const busy = busyKey === `${event.event_id}:${sponsor.index}`;
                  return (
                    <li
                      key={`${event.event_id}-${sponsor.index}`}
                      className="flex flex-col gap-3 rounded-lg border border-border bg-bg-1 p-3 sm:flex-row sm:items-center sm:justify-between"
                      data-testid={`sponsor-row-${sponsor.index}`}
                    >
                      <div className="flex min-w-0 flex-1 items-start gap-3">
                        {sponsor.logo ? (
                          <CloudinaryImage
                            publicId={sponsor.logo}
                            width={64}
                            ratio="1/1"
                            alt={t("logoAlt", { name: sponsor.name })}
                            className="size-16 shrink-0 rounded-md object-contain"
                          />
                        ) : null}
                        <div className="min-w-0">
                          <p className="font-medium text-text">{sponsor.name}</p>
                          {sponsor.tagline ? (
                            <p className="text-sm text-muted">
                              {t("tagline", { text: sponsor.tagline })}
                            </p>
                          ) : null}
                          {sponsor.link_url ? (
                            <p className="truncate text-sm text-muted">
                              {t("link", { url: sponsor.link_url })}
                            </p>
                          ) : null}
                        </div>
                      </div>
                      <div className="flex flex-wrap gap-2">
                        <button
                          type="button"
                          className="inline-flex min-h-11 items-center justify-center rounded-md bg-primary px-4 text-sm font-semibold text-[var(--primary-btn-fg)] disabled:opacity-50"
                          disabled={busy}
                          onClick={() => void submitDecision(event.event_id, sponsor, "approved")}
                        >
                          {t("approve")}
                        </button>
                        <button
                          type="button"
                          className="inline-flex min-h-11 items-center justify-center rounded-md border border-danger px-4 text-sm font-medium text-danger disabled:opacity-50"
                          disabled={busy}
                          onClick={() => {
                            setRejectTarget({ eventId: event.event_id, sponsor });
                            setRejectNote("");
                          }}
                        >
                          {t("reject")}
                        </button>
                      </div>
                    </li>
                  );
                })}
              </ul>
            </li>
          ))}
        </ul>
      )}
      {rejectTarget ? (
        <div
          className="fixed inset-0 z-50 flex items-end justify-center bg-black/40 p-4 sm:items-center"
          role="dialog"
          aria-modal="true"
          aria-labelledby="sponsor-reject-title"
        >
          <div className="w-full max-w-md rounded-lg border border-border bg-surface p-4 shadow-lg">
            <h2 id="sponsor-reject-title" className="font-display text-lg text-text">
              {t("rejectTitle")}
            </h2>
            <p className="mt-2 text-sm text-muted">{t("rejectHint")}</p>
            <label className="mt-4 block text-sm text-text">
              {t("noteLabel")}
              <textarea
                className="mt-1 w-full rounded-md border border-border px-3 py-2 text-sm"
                rows={3}
                value={rejectNote}
                onChange={(event) => setRejectNote(event.target.value)}
                placeholder={t("notePlaceholder")}
              />
            </label>
            <div className="mt-4 flex flex-wrap justify-end gap-2">
              <button
                type="button"
                className="inline-flex min-h-11 items-center rounded-md border border-border px-4 text-sm"
                onClick={() => setRejectTarget(null)}
              >
                {t("cancel")}
              </button>
              <button
                type="button"
                className="inline-flex min-h-11 items-center rounded-md bg-danger px-4 text-sm font-medium text-on-danger"
                onClick={() =>
                  void submitDecision(
                    rejectTarget.eventId,
                    rejectTarget.sponsor,
                    "rejected",
                    rejectNote,
                  )
                }
              >
                {t("confirmReject")}
              </button>
            </div>
          </div>
        </div>
      ) : null}
    </div>
  );
}
