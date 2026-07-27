"use client";

import { useSession } from "@vergeo/auth/use-session";
import { formatK } from "@vergeo/i18n";
import Link from "next/link";
import { useTranslations } from "next-intl";
import { useCallback, useEffect, useMemo, useState } from "react";

import { VendorEmptyState, VendorErrorState } from "../../_components/async-state";
import { createIntakeClient, type IntakeSessionSummary } from "../_lib/intake-client";
import { Badge, Spinner } from "../_lib/ui";

type IntakeSessionListProps = {
  locale: string;
};

/** Draft sessions the vendor still has to act on sort to the top. */
const ACTIONABLE: ReadonlySet<string> = new Set([
  "ready_for_vendor_review",
  "needs_details",
  "collecting",
]);

function statusTone(status: string): "free" | "sold_out" | "new" {
  if (status === "approved") return "free";
  if (status === "rejected" || status === "expired") return "sold_out";
  return "new";
}

export function IntakeSessionList({ locale }: IntakeSessionListProps) {
  const t = useTranslations("vendor");
  const { session, loading: sessionLoading } = useSession();
  const [sessions, setSessions] = useState<IntakeSessionSummary[]>([]);
  const [loading, setLoading] = useState(true);
  const [failed, setFailed] = useState(false);
  const [reloadKey, setReloadKey] = useState(0);

  const getToken = useCallback(() => session?.access_token ?? null, [session?.access_token]);
  const intakeClient = useMemo(() => createIntakeClient(getToken), [getToken]);

  useEffect(() => {
    if (sessionLoading) return;
    if (!session) {
      setLoading(false);
      return;
    }
    let cancelled = false;
    setLoading(true);
    setFailed(false);
    intakeClient
      .listSessions()
      .then((rows) => {
        if (!cancelled) setSessions(rows);
      })
      .catch(() => {
        if (!cancelled) {
          setSessions([]);
          setFailed(true);
        }
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [intakeClient, reloadKey, session, sessionLoading]);

  const ordered = useMemo(
    () =>
      [...sessions].sort((left, right) => {
        const leftActionable = ACTIONABLE.has(left.status) ? 0 : 1;
        const rightActionable = ACTIONABLE.has(right.status) ? 0 : 1;
        return leftActionable - rightActionable;
      }),
    [sessions],
  );

  if (loading || sessionLoading) {
    return (
      <div className="flex min-h-[40vh] items-center justify-center">
        <Spinner label={t("intake.loading")} />
      </div>
    );
  }

  if (failed) {
    return (
      <VendorErrorState
        title={t("intake.error.title")}
        retryLabel={t("intake.error.retry")}
        onRetry={() => setReloadKey((key) => key + 1)}
        data-testid="intake-error-state"
      />
    );
  }

  return (
    <section className="flex flex-col gap-4 p-4">
      <header className="flex flex-col gap-1">
        <h1 className="text-xl font-semibold">{t("intake.title")}</h1>
        <p className="text-sm text-muted-foreground">{t("intake.intro")}</p>
      </header>

      {ordered.length === 0 ? (
        <VendorEmptyState
          title={t("intake.empty.title")}
          body={t("intake.empty.body")}
          data-testid="intake-empty-state"
        />
      ) : (
        <ul className="flex flex-col gap-3" data-testid="intake-session-list">
          {ordered.map((row) => (
            <li key={row.id}>
              <Link
                href={`/${locale}/intake/${row.id}`}
                className="flex min-h-[44px] flex-col gap-1 rounded-lg border border-border p-3 focus-visible:outline focus-visible:outline-2"
              >
                <div className="flex items-center justify-between gap-2">
                  <span className="font-medium">{row.title ?? t("intake.fields.title")}</span>
                  <Badge
                    variant={statusTone(row.status)}
                    label={t(`intake.status.${row.status}`)}
                  />
                </div>
                <div className="flex items-center justify-between gap-2 text-sm text-muted-foreground">
                  <span>{row.price_ngwee === null ? "—" : formatK(row.price_ngwee)}</span>
                  {row.pending_request_count > 0 ? <span>{t("intake.detail.missing")}</span> : null}
                </div>
              </Link>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
