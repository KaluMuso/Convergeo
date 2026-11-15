"use client";

import Link from "next/link";
import { useTranslations } from "next-intl";
import { useEffect, useState } from "react";

import { Spinner } from "../../../listings/new/_lib/ui";
import {
  type CollabFlagStatus,
  type CollabRequest,
} from "../_lib/collab-client";

import {
  CollabStatusBadge,
  ReadinessMeter,
  useCollabClient,
  useCollabErrorText,
} from "./collab-parts";

type Props = { locale: string; role: "proposer" | "organiser" };

/**
 * Proposer view ("my proposals") or organiser inbox (incoming requests). The same
 * list component serves both so status badges and readiness read identically.
 */
export function CollabList({ locale, role }: Props) {
  const t = useTranslations("vendor");
  const { client, hasSession, sessionLoading } = useCollabClient();
  const errorText = useCollabErrorText();
  const [flag, setFlag] = useState<CollabFlagStatus | null>(null);
  const [items, setItems] = useState<CollabRequest[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (sessionLoading) return;
    if (!hasSession) {
      setLoading(false);
      return;
    }
    let cancelled = false;
    setLoading(true);
    client
      .getStatus()
      .then(async (status) => {
        if (cancelled) return;
        setFlag(status);
        if (!status.enabled) return;
        const response = await client.listRequests(role);
        if (!cancelled) {
          setItems(response.items);
          setError(null);
        }
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
  }, [client, hasSession, sessionLoading, role, errorText]);

  if (sessionLoading || loading) {
    return (
      <div className="flex min-h-[40vh] items-center justify-center">
        <Spinner label={t("events.collab.loading")} />
      </div>
    );
  }
  if (flag && !flag.enabled) {
    return (
      <p className="text-sm text-text-2" data-testid="collab-disabled">
        {t("events.collab.errors.disabled")}
      </p>
    );
  }

  const isInbox = role === "organiser";
  return (
    <div
      className="flex flex-col gap-3"
      data-testid={isInbox ? "collab-inbox" : "collab-hub"}
    >
      <header className="flex flex-col gap-1">
        <h1 className="text-xl font-semibold text-text">
          {isInbox
            ? t("events.collab.inbox.title")
            : t("events.collab.hub.title")}
        </h1>
        <p className="text-sm text-text-2">
          {isInbox
            ? t("events.collab.inbox.intro")
            : t("events.collab.hub.intro")}
        </p>
        {!isInbox ? (
          <div className="flex flex-wrap gap-2 pt-1">
            <Link
              href={`/${locale}/events/collaborate/new`}
              data-testid="collab-new"
              className="inline-flex min-h-11 items-center rounded-md bg-primary px-4 text-sm font-medium text-surface"
            >
              {t("events.collab.hub.newCta")}
            </Link>
            {flag?.can_organise ? (
              <Link
                href={`/${locale}/events/requests`}
                className="inline-flex min-h-11 items-center rounded-md border border-border px-4 text-sm font-medium"
              >
                {t("events.collab.hub.inboxCta")}
              </Link>
            ) : null}
          </div>
        ) : null}
      </header>

      {error ? (
        <p role="alert" className="text-sm text-danger">
          {error}
        </p>
      ) : null}

      {items.length === 0 ? (
        <div className="rounded-lg border border-dashed border-border p-6 text-center">
          <p className="text-sm text-text-2">
            {isInbox
              ? t("events.collab.inbox.empty")
              : t("events.collab.hub.empty")}
          </p>
        </div>
      ) : (
        <ul className="flex flex-col gap-3">
          {items.map((item) => {
            const title =
              typeof item.event_draft.title === "string" &&
              item.event_draft.title
                ? item.event_draft.title
                : t("events.collab.untitled");
            const other = isInbox ? item.proposer : item.organiser;
            return (
              <li key={item.id} className="rounded-lg border border-border p-3">
                <div className="flex items-start justify-between gap-2">
                  <div className="min-w-0">
                    <p className="truncate font-medium text-text">{title}</p>
                    <p className="text-xs text-text-2">
                      {isInbox
                        ? t("events.collab.list.from", {
                            name: other.display_name,
                          })
                        : t("events.collab.list.to", {
                            name: other.display_name,
                          })}
                    </p>
                  </div>
                  <CollabStatusBadge status={item.status} />
                </div>
                <div className="mt-2">
                  <ReadinessMeter pct={item.readiness_pct} />
                </div>
                <Link
                  href={`/${locale}/events/collaborate/${item.id}`}
                  className="mt-3 inline-flex min-h-11 w-full items-center justify-center rounded-md border border-border px-4 text-sm font-medium"
                >
                  {t("events.collab.list.open")}
                </Link>
              </li>
            );
          })}
        </ul>
      )}
    </div>
  );
}
