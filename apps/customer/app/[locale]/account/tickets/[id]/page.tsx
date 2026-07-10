"use client";

import { useSession } from "@vergeo/auth/use-session";
import { ApiError, createApiClient } from "@vergeo/config";
import Link from "next/link";
import { useParams } from "next/navigation";
import { useTranslations } from "next-intl";
import { useCallback, useEffect, useMemo, useState } from "react";

type WalletEvent = {
  id: string;
  title: string;
  venue: string | null;
  slug: string;
};

type WalletInstance = {
  id: string;
  starts_at: string;
};

type WalletTicketType = {
  id: string;
  name: string;
  kind: string;
};

type WalletQr = {
  window: number;
  code: string;
  qr_payload: string;
  seconds_remaining: number;
};

type WalletTicketDetail = {
  id: string;
  status: "issued" | "checked_in" | "transferred" | "void";
  pin: string | null;
  pin_available: boolean;
  qr: WalletQr | null;
  event: WalletEvent;
  instance: WalletInstance;
  ticket_type: WalletTicketType;
};

type HorizonEntry = {
  window: number;
  code: string;
  qr_payload: string;
};

type HorizonCache = {
  ticket_id: string;
  from_window: number;
  last_window: number;
  pin: string | null;
  entries: HorizonEntry[];
  cached_at: string;
};

const HORIZON_STORAGE_PREFIX = "vergeo5:ticket-horizon:";
const WINDOW_SECONDS = 60;

function getApiBaseUrl(): string {
  return process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";
}

function currentWindow(nowMs: number = Date.now()): number {
  return Math.floor(nowMs / 1000 / WINDOW_SECONDS);
}

function secondsRemaining(nowMs: number = Date.now()): number {
  const elapsed = Math.floor(nowMs / 1000) % WINDOW_SECONDS;
  return WINDOW_SECONDS - elapsed;
}

function readHorizonCache(ticketId: string): HorizonCache | null {
  if (typeof window === "undefined") {
    return null;
  }
  const raw = window.localStorage.getItem(`${HORIZON_STORAGE_PREFIX}${ticketId}`);
  if (!raw) {
    return null;
  }
  try {
    return JSON.parse(raw) as HorizonCache;
  } catch {
    return null;
  }
}

function writeHorizonCache(cache: HorizonCache): void {
  window.localStorage.setItem(`${HORIZON_STORAGE_PREFIX}${cache.ticket_id}`, JSON.stringify(cache));
}

function useOnline(): boolean {
  const [online, setOnline] = useState(typeof navigator !== "undefined" ? navigator.onLine : true);

  useEffect(() => {
    const onOnline = () => setOnline(true);
    const onOffline = () => setOnline(false);
    window.addEventListener("online", onOnline);
    window.addEventListener("offline", onOffline);
    return () => {
      window.removeEventListener("online", onOnline);
      window.removeEventListener("offline", onOffline);
    };
  }, []);

  return online;
}

function ProgressRing({ progress }: { progress: number }) {
  const radius = 46;
  const circumference = 2 * Math.PI * radius;
  const offset = circumference * (1 - progress);

  return (
    <svg
      aria-hidden="true"
      className="pointer-events-none absolute inset-0 h-full w-full -rotate-90"
      viewBox="0 0 100 100"
    >
      <circle
        cx="50"
        cy="50"
        r={radius}
        fill="none"
        stroke="currentColor"
        className="text-border"
        strokeWidth="6"
      />
      <circle
        cx="50"
        cy="50"
        r={radius}
        fill="none"
        stroke="currentColor"
        className="text-primary"
        strokeWidth="6"
        strokeLinecap="round"
        strokeDasharray={circumference}
        strokeDashoffset={offset}
      />
    </svg>
  );
}

function QrPayloadDisplay({ payload, label }: { payload: string; label: string }) {
  return (
    <div
      aria-label={label}
      className="flex h-full w-full items-center justify-center rounded bg-surface p-2"
      role="img"
    >
      <p className="break-all text-center font-mono text-[10px] leading-tight text-display-ink">
        {payload}
      </p>
    </div>
  );
}

export default function AccountTicketDetailPage() {
  const params = useParams<{ locale: string; id: string }>();
  const locale = params.locale;
  const ticketId = params.id;
  const t = useTranslations("events.wallet.detail");
  const online = useOnline();
  const { session } = useSession();

  const [detail, setDetail] = useState<WalletTicketDetail | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [nowMs, setNowMs] = useState(Date.now());
  const [horizonCache, setHorizonCache] = useState<HorizonCache | null>(null);
  const [syncingHorizon, setSyncingHorizon] = useState(false);

  const client = useMemo(
    () =>
      createApiClient({
        baseUrl: getApiBaseUrl(),
        getToken: () => session?.access_token ?? null,
      }),
    [session?.access_token],
  );

  const syncHorizon = useCallback(async () => {
    if (!ticketId || !session?.access_token) {
      return;
    }
    setSyncingHorizon(true);
    try {
      const body = await client.request<{
        ticket_id: string;
        from_window: number;
        last_window: number;
        pin: string | null;
        entries: HorizonEntry[];
      }>(`/account/tickets/${ticketId}/horizon`);
      const cache: HorizonCache = {
        ticket_id: body.ticket_id,
        from_window: body.from_window,
        last_window: body.last_window,
        pin: body.pin,
        entries: body.entries,
        cached_at: new Date().toISOString(),
      };
      writeHorizonCache(cache);
      setHorizonCache(cache);
    } catch {
      // offline or ticket unusable — keep existing cache
    } finally {
      setSyncingHorizon(false);
    }
  }, [client, session?.access_token, ticketId]);

  useEffect(() => {
    setHorizonCache(readHorizonCache(ticketId));
  }, [ticketId]);

  useEffect(() => {
    if (!session?.access_token || !ticketId) {
      return;
    }
    let cancelled = false;
    setLoading(true);
    client
      .request<WalletTicketDetail>(`/account/tickets/${ticketId}`)
      .then((body) => {
        if (!cancelled) {
          setDetail(body);
          setError(null);
        }
      })
      .catch((fetchError: unknown) => {
        if (!cancelled) {
          if (fetchError instanceof ApiError && fetchError.status === 404) {
            setError("not_found");
          } else {
            setError("load_failed");
          }
        }
      })
      .finally(() => {
        if (!cancelled) {
          setLoading(false);
        }
      });
    return () => {
      cancelled = true;
    };
  }, [client, session?.access_token, ticketId]);

  useEffect(() => {
    if (!online || !detail || detail.status !== "issued") {
      return;
    }
    void syncHorizon();
  }, [detail, online, syncHorizon]);

  useEffect(() => {
    if (!online || !detail || detail.status !== "issued") {
      return;
    }
    const cached = horizonCache ?? readHorizonCache(ticketId);
    const activeWindow = currentWindow();
    if (!cached || activeWindow > cached.last_window) {
      void syncHorizon();
    }
  }, [detail, horizonCache, nowMs, online, syncHorizon, ticketId]);

  useEffect(() => {
    if (!online || !session?.access_token || !ticketId) {
      return;
    }
    const timer = window.setInterval(() => {
      void client
        .request<WalletTicketDetail>(`/account/tickets/${ticketId}`)
        .then(setDetail)
        .catch(() => undefined);
    }, WINDOW_SECONDS * 1000);
    return () => window.clearInterval(timer);
  }, [client, online, session?.access_token, ticketId]);

  useEffect(() => {
    const timer = window.setInterval(() => setNowMs(Date.now()), 1000);
    return () => window.clearInterval(timer);
  }, []);

  const windowNow = currentWindow(nowMs);
  const remaining = secondsRemaining(nowMs);
  const progress = (WINDOW_SECONDS - remaining) / WINDOW_SECONDS;

  const livePayload = useMemo(() => {
    if (!detail || detail.status !== "issued") {
      return null;
    }
    const cached = horizonCache ?? readHorizonCache(ticketId);
    const cachedEntry = cached?.entries.find((item) => item.window === windowNow);
    if (cachedEntry) {
      return cachedEntry.qr_payload;
    }
    if (online && detail.qr && detail.qr.window === windowNow) {
      return detail.qr.qr_payload;
    }
    return null;
  }, [detail, horizonCache, online, ticketId, windowNow]);

  const horizonExpired =
    !online &&
    detail?.status === "issued" &&
    (horizonCache?.last_window ?? -1) < windowNow &&
    livePayload == null;

  const pinValue = detail?.pin ?? horizonCache?.pin ?? null;

  if (loading) {
    return <p className="text-sm text-text-2">{t("syncHorizon")}</p>;
  }

  if (error === "not_found" || !detail) {
    return (
      <section className="space-y-3 rounded border border-border bg-surface p-6 text-center">
        <p className="text-sm text-text-2">{t("voidBanner")}</p>
        <Link
          href={`/${locale}/account/tickets`}
          className="inline-flex min-h-11 items-center justify-center rounded border border-primary px-4 text-sm font-medium text-primary"
        >
          {t("back")}
        </Link>
      </section>
    );
  }

  const startsAt = new Date(detail.instance.starts_at).toLocaleString(locale, {
    dateStyle: "full",
    timeStyle: "short",
  });

  return (
    <section className="space-y-5">
      <Link
        href={`/${locale}/account/tickets`}
        className="inline-flex min-h-11 items-center text-sm font-medium text-primary"
      >
        {t("back")}
      </Link>

      {!online ? (
        <div
          className="rounded border border-warning/40 bg-warning/10 px-4 py-3 text-sm text-display-ink"
          role="status"
        >
          <p className="font-medium">{t("offlineTitle")}</p>
          <p className="text-text-2">{horizonExpired ? t("offlineExpired") : t("offlineBody")}</p>
        </div>
      ) : null}

      {detail.status === "transferred" ? (
        <p className="rounded border border-border bg-bg-2 px-4 py-3 text-sm text-text-2">
          {t("transferBanner")}
        </p>
      ) : null}

      {detail.status === "void" ? (
        <p className="rounded border border-border bg-bg-2 px-4 py-3 text-sm text-text-2">
          {t("voidBanner")}
        </p>
      ) : null}

      <header className="space-y-1 rounded border border-border bg-surface p-4">
        <p className="text-xs font-medium uppercase tracking-wide text-text-2">{t("eventLabel")}</p>
        <h2 className="font-display text-h2 text-display-ink">{detail.event.title}</h2>
        <dl className="mt-3 space-y-2 text-sm text-text-2">
          {detail.event.venue ? (
            <div>
              <dt className="font-medium text-display-ink">{t("venueLabel")}</dt>
              <dd>{detail.event.venue}</dd>
            </div>
          ) : null}
          <div>
            <dt className="font-medium text-display-ink">{t("startsLabel")}</dt>
            <dd>{startsAt}</dd>
          </div>
          <div>
            <dt className="font-medium text-display-ink">{t("typeLabel")}</dt>
            <dd>{detail.ticket_type.name}</dd>
          </div>
        </dl>
        <p className="mt-2 text-sm font-medium text-primary">{t(`status.${detail.status}`)}</p>
      </header>

      {detail.status === "issued" ? (
        <section
          aria-labelledby="ticket-qr-heading"
          className="space-y-4 rounded border border-border bg-surface p-4"
        >
          <div className="flex items-center justify-between gap-2">
            <h3 id="ticket-qr-heading" className="font-display text-h3 text-display-ink">
              {t("qrLabel")}
            </h3>
            <p className="font-mono text-xs text-text-2">
              {t("refreshIn", { seconds: remaining })}
            </p>
          </div>

          <div className="relative mx-auto aspect-square w-full max-w-[240px] p-2">
            <ProgressRing progress={progress} />
            <div className="absolute inset-3 rounded bg-surface p-2">
              {livePayload ? (
                <QrPayloadDisplay label={t("qrAria")} payload={livePayload} />
              ) : (
                <div className="flex h-full items-center justify-center text-center text-xs text-text-2">
                  {syncingHorizon ? t("syncHorizon") : t("offlineExpired")}
                </div>
              )}
            </div>
          </div>
        </section>
      ) : null}

      <section
        aria-labelledby="ticket-pin-heading"
        className="space-y-2 rounded border border-border bg-surface p-4"
      >
        <h3 id="ticket-pin-heading" className="font-display text-h3 text-display-ink">
          {t("pinLabel")}
        </h3>
        {pinValue ? (
          <p
            aria-label={t("pinAria", { pin: pinValue })}
            className="rounded bg-bg-2 p-3 text-center font-mono text-2xl tracking-[0.35em] text-display-ink"
          >
            {pinValue}
          </p>
        ) : (
          <p className="text-sm text-text-2">{t("pinUnavailable")}</p>
        )}
      </section>
    </section>
  );
}
