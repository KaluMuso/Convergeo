"use client";

import Link from "next/link";
import { useTranslations } from "next-intl";
import { useCallback, useEffect, useState } from "react";

import { classifyAdminRequestError } from "./admin-request";
import { dashboardApi } from "./api";
import { countOverdue, dispatchCutoffClock, type TodayTone, toneFor } from "./today-model";

type Loaded =
  | { state: "loading" }
  | { state: "denied" }
  | { state: "error" }
  | { state: "ok"; count: number; overdue: number };

type ReadyOrdersResponse = { flag_enabled: boolean; ready_orders: unknown[] };

const TONE_CLASS: Record<TodayTone, string> = {
  clear: "border-border bg-surface",
  attention: "border-warning/50 bg-warning/5",
  urgent: "border-danger/50 bg-danger/5",
};

const TONE_NUMBER: Record<TodayTone, string> = {
  clear: "text-success",
  attention: "text-text",
  urgent: "text-danger",
};

async function loadList(path: string): Promise<Loaded> {
  try {
    const rows = await dashboardApi.request<Array<{ sla_badge?: string | null }>>(path);
    return { state: "ok", count: rows.length, overdue: countOverdue(rows) };
  } catch (error) {
    return classifyAdminRequestError(error).kind === "permission"
      ? { state: "denied" }
      : { state: "error" };
  }
}

type TodayCardProps = {
  href: string;
  title: string;
  hint: string;
  loaded: Loaded;
  /** Escalate tone (overdue SLA, past cut-off). */
  escalate?: boolean;
  /** Extra line under the number, e.g. "2 overdue". */
  detail?: string | null;
  testId: string;
};

function TodayCard({
  href,
  title,
  hint,
  loaded,
  escalate = false,
  detail,
  testId,
}: TodayCardProps) {
  const t = useTranslations("admin.today");
  const count = loaded.state === "ok" ? loaded.count : 0;
  const tone: TodayTone = loaded.state === "ok" ? toneFor(count, escalate) : "clear";
  const cardClass = loaded.state === "ok" ? TONE_CLASS[tone] : "border-border bg-surface";

  return (
    <Link
      href={href}
      data-testid={testId}
      className={`group flex min-h-24 flex-col justify-between gap-2 rounded-lg border p-4 focus-visible:outline focus-visible:outline-2 focus-visible:outline-primary ${cardClass}`}
    >
      <div className="flex items-start justify-between gap-3">
        <h3 className="text-sm font-semibold text-text">{title}</h3>
        {loaded.state === "loading" ? (
          <span role="status" className="h-8 w-10 animate-pulse rounded bg-bg-2">
            <span className="sr-only">{t("loading")}</span>
          </span>
        ) : loaded.state === "ok" ? (
          <span className={`font-mono text-3xl font-semibold leading-none ${TONE_NUMBER[tone]}`}>
            {count}
          </span>
        ) : (
          <span className="text-xs font-medium text-warning">
            {loaded.state === "denied" ? t("noAccess") : t("unavailable")}
          </span>
        )}
      </div>
      <p className="text-xs text-muted">
        {loaded.state === "ok" ? (count === 0 ? t("allClear") : (detail ?? hint)) : hint}
      </p>
      <span className="text-xs font-medium text-primary group-hover:underline">
        {loaded.state === "error" || loaded.state === "denied" ? t("openList") : t("open")}
      </span>
    </Link>
  );
}

type TodayBoardProps = {
  locale: string;
  /** Orders in `placed` from /admin/dashboard; null when that call failed. */
  placedCount: number | null;
  placedLoading: boolean;
};

export function TodayBoard({ locale, placedCount, placedLoading }: TodayBoardProps) {
  const t = useTranslations("admin.today");
  const [kyc, setKyc] = useState<Loaded>({ state: "loading" });
  const [disputes, setDisputes] = useState<Loaded>({ state: "loading" });
  const [ready, setReady] = useState<Loaded>({ state: "loading" });
  const [now, setNow] = useState<Date | null>(null);

  const load = useCallback(async () => {
    setKyc({ state: "loading" });
    setDisputes({ state: "loading" });
    setReady({ state: "loading" });
    const [kycResult, disputeResult, readyResult] = await Promise.all([
      loadList("/admin/vendors?status=pending"),
      loadList("/admin/disputes"),
      dashboardApi
        .request<ReadyOrdersResponse>("/admin/dispatch/board")
        .then((board): Loaded => ({
          state: "ok",
          count: board.ready_orders.length,
          overdue: 0,
        }))
        .catch((error: unknown): Loaded =>
          classifyAdminRequestError(error).kind === "permission"
            ? { state: "denied" }
            : { state: "error" },
        ),
    ]);
    setKyc(kycResult);
    setDisputes(disputeResult);
    setReady(readyResult);
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  useEffect(() => {
    setNow(new Date());
    const id = setInterval(() => setNow(new Date()), 30_000);
    return () => clearInterval(id);
  }, []);

  const clock = now ? dispatchCutoffClock(now) : null;
  const placed: Loaded = placedLoading
    ? { state: "loading" }
    : placedCount === null
      ? { state: "error" }
      : { state: "ok", count: placedCount, overdue: 0 };

  const clockText = clock
    ? clock.passed
      ? t("cutoffPassed")
      : t("cutoffIn", { hours: clock.hours, minutes: clock.minutes })
    : "";

  return (
    <section aria-labelledby="today-heading" className="space-y-3" data-testid="today-board">
      <header className="flex flex-wrap items-end justify-between gap-2">
        <div className="space-y-1">
          <h2 id="today-heading" className="font-serif text-lg text-text">
            {t("title")}
          </h2>
          <p className="text-xs text-muted">{t("subtitle")}</p>
        </div>
        <button
          type="button"
          onClick={() => void load()}
          className="inline-flex min-h-11 items-center rounded-md border border-border px-4 text-sm"
        >
          {t("refresh")}
        </button>
      </header>

      <ul className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
        <li>
          <TodayCard
            testId="today-placed"
            href={`/${locale}/orders?status=placed`}
            title={t("placed.title")}
            hint={t("placed.hint")}
            loaded={placed}
          />
        </li>
        <li>
          <TodayCard
            testId="today-dispatch"
            href={`/${locale}/orders/dispatch`}
            title={t("dispatch.title")}
            hint={clockText ? `${t("dispatch.hint")} ${clockText}` : t("dispatch.hint")}
            detail={clockText}
            loaded={ready}
            escalate={clock ? clock.passed || clock.urgent : false}
          />
        </li>
        <li>
          <TodayCard
            testId="today-kyc"
            href={`/${locale}/kyc`}
            title={t("kyc.title")}
            hint={t("kyc.hint")}
            loaded={kyc}
            escalate={kyc.state === "ok" && kyc.overdue > 0}
            detail={kyc.state === "ok" ? t("overdueCount", { count: kyc.overdue }) : null}
          />
        </li>
        <li>
          <TodayCard
            testId="today-disputes"
            href={`/${locale}/disputes`}
            title={t("disputes.title")}
            hint={t("disputes.hint")}
            loaded={disputes}
            escalate={disputes.state === "ok" && disputes.overdue > 0}
            detail={disputes.state === "ok" ? t("overdueCount", { count: disputes.overdue }) : null}
          />
        </li>
        <li>
          <Link
            href={`/${locale}/support`}
            data-testid="today-notifications"
            className="flex min-h-24 flex-col justify-between gap-2 rounded-lg border border-border bg-surface p-4 focus-visible:outline focus-visible:outline-2 focus-visible:outline-primary"
          >
            <h3 className="text-sm font-semibold text-text">{t("notifications.title")}</h3>
            <p className="text-xs text-muted">{t("notifications.hint")}</p>
            <span className="text-xs font-medium text-primary">{t("openList")}</span>
          </Link>
        </li>
      </ul>
    </section>
  );
}
