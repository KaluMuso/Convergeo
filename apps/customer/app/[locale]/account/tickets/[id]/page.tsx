import { ApiError } from "@vergeo/config";
import { loadNamespace, LOCALES, type Locale } from "@vergeo/i18n";
import Link from "next/link";
import { notFound } from "next/navigation";
import { createTranslator, type AbstractIntlMessages } from "next-intl";
import { getMessages, setRequestLocale } from "next-intl/server";

import { getAccountAccessToken } from "../../_components/account-server";

import type { Metadata } from "next";

export const metadata: Metadata = {
  robots: {
    index: false,
    follow: false,
  },
};

type PageProps = {
  params: Promise<{ locale: string; id: string }>;
};

type WalletTicketDetail = {
  id: string;
  status: "issued" | "checked_in" | "transferred" | "void";
  holder_name: string | null;
  pin: string | null;
  pin_available: boolean;
  qr: {
    window: number;
    code: string;
    qr_payload: string;
    seconds_remaining: number;
  } | null;
  event: {
    id: string;
    title: string;
    venue: string | null;
    slug: string;
  };
  instance: {
    id: string;
    starts_at: string;
  };
  ticket_type: {
    id: string;
    name: string;
    kind: string;
  };
};

type HorizonResponse = {
  ticket_id: string;
  from_window: number;
  last_window: number;
  pin: string | null;
  entries: Array<{
    window: number;
    code: string;
    qr_payload: string;
  }>;
};

function getApiBaseUrl(): string {
  return process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";
}

async function fetchTicketDetail(
  accessToken: string,
  ticketId: string,
): Promise<WalletTicketDetail> {
  const response = await fetch(`${getApiBaseUrl()}/account/tickets/${ticketId}`, {
    headers: {
      Authorization: `Bearer ${accessToken}`,
      Accept: "application/json",
    },
    cache: "no-store",
  });
  if (response.status === 404) {
    throw new ApiError("not_found", "Ticket not found", { status: 404 });
  }
  if (!response.ok) {
    throw new Error(`Ticket detail failed: ${response.status}`);
  }
  return (await response.json()) as WalletTicketDetail;
}

async function fetchHorizon(
  accessToken: string,
  ticketId: string,
): Promise<HorizonResponse | null> {
  const response = await fetch(`${getApiBaseUrl()}/account/tickets/${ticketId}/horizon`, {
    headers: {
      Authorization: `Bearer ${accessToken}`,
      Accept: "application/json",
    },
    cache: "no-store",
  });
  if (!response.ok) {
    return null;
  }
  return (await response.json()) as HorizonResponse;
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
        data-ticket-ring="progress"
      />
    </svg>
  );
}

export function generateStaticParams() {
  return LOCALES.map((locale) => ({ locale, id: "00000000-0000-0000-0000-000000000000" }));
}

export default async function AccountTicketDetailPage({ params }: PageProps) {
  const { locale, id } = await params;

  if (!LOCALES.includes(locale as Locale)) {
    return null;
  }

  setRequestLocale(locale);
  const accessToken = await getAccountAccessToken(locale);
  const baseMessages = await getMessages();
  const eventsMessages = await loadNamespace(locale as Locale, "events");
  const messages = { ...baseMessages, events: eventsMessages } as AbstractIntlMessages;
  const t = createTranslator({ locale, messages, namespace: "events.wallet.detail" }) as (
    key: string,
    values?: Record<string, string | number>,
  ) => string;

  let detail: WalletTicketDetail;
  try {
    detail = await fetchTicketDetail(accessToken, id);
  } catch (error) {
    if (error instanceof ApiError && error.status === 404) {
      notFound();
    }
    throw error;
  }

  const horizon = detail.status === "issued" ? await fetchHorizon(accessToken, id) : null;
  const remaining = detail.qr?.seconds_remaining ?? 60;
  const progress = (60 - remaining) / 60;
  const livePayload = detail.qr?.qr_payload ?? null;

  const startsAt = new Date(detail.instance.starts_at).toLocaleString(locale, {
    dateStyle: "full",
    timeStyle: "short",
  });

  const walletScript = JSON.stringify({
    ticketId: id,
    horizon,
    labels: {
      refreshInTemplate: t("refreshIn", { seconds: "__SEC__" }),
      offlineTitle: t("offlineTitle"),
      offlineBody: t("offlineBody"),
      offlineExpired: t("offlineExpired"),
    },
  });

  return (
    <section className="space-y-5">
      <Link
        href={`/${locale}/account/tickets`}
        className="inline-flex min-h-11 items-center text-sm font-medium text-primary"
      >
        {t("back")}
      </Link>

      <div
        className="hidden rounded border border-warning/40 bg-warning/10 px-4 py-3 text-sm text-display-ink"
        data-ticket-offline-banner
        role="status"
      >
        <p className="font-medium">{t("offlineTitle")}</p>
        <p className="text-text-2" data-ticket-offline-body>
          {t("offlineBody")}
        </p>
      </div>

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
          {detail.holder_name ? (
            <div>
              <dt className="font-medium text-display-ink">{t("holderLabel")}</dt>
              <dd>{detail.holder_name}</dd>
            </div>
          ) : null}
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
            <p className="font-mono text-xs text-text-2" data-ticket-countdown>
              {t("refreshIn", { seconds: remaining })}
            </p>
          </div>

          <div className="relative mx-auto aspect-square w-full max-w-[240px] p-2">
            <ProgressRing progress={progress} />
            <div className="absolute inset-3 rounded bg-surface p-2">
              {livePayload ? (
                <div
                  aria-label={t("qrAria")}
                  className="flex h-full w-full items-center justify-center rounded bg-surface p-2"
                  data-ticket-qr-payload
                  role="img"
                >
                  <p className="break-all text-center font-mono text-[10px] leading-tight text-display-ink">
                    {livePayload}
                  </p>
                </div>
              ) : (
                <div className="flex h-full items-center justify-center text-center text-xs text-text-2">
                  {t("offlineExpired")}
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
        {detail.pin ? (
          <p
            aria-label={t("pinAria", { pin: detail.pin })}
            className="rounded bg-bg-2 p-3 text-center font-mono text-2xl tracking-[0.35em] text-display-ink"
            data-ticket-pin
          >
            {detail.pin}
          </p>
        ) : (
          <p className="text-sm text-text-2">{t("pinUnavailable")}</p>
        )}
      </section>

      {detail.status === "issued" ? (
        <script
          dangerouslySetInnerHTML={{
            __html: `(function(){var cfg=${walletScript};var KEY="vergeo5:ticket-horizon:"+cfg.ticketId;var WINDOW=60;var R=46;var C=2*Math.PI*R;function cw(){return Math.floor(Date.now()/1000/WINDOW)}function sr(){return WINDOW-(Math.floor(Date.now()/1000)%WINDOW)}function read(){try{return JSON.parse(localStorage.getItem(KEY)||"null")}catch(e){return null}}function write(h){if(h)localStorage.setItem(KEY,JSON.stringify(h))}function payloadFor(w){var c=read();if(c&&Array.isArray(c.entries)){var e=c.entries.find(function(x){return x.window===w});if(e)return e.qr_payload}if(cfg.horizon&&Array.isArray(cfg.horizon.entries)){var e2=cfg.horizon.entries.find(function(x){return x.window===w});if(e2)return e2.qr_payload}return null}function setOffline(on,expired){var b=document.querySelector("[data-ticket-offline-banner]");var body=document.querySelector("[data-ticket-offline-body]");if(!b||!body)return;b.classList.toggle("hidden",!on);if(on)body.textContent=expired?cfg.labels.offlineExpired:cfg.labels.offlineBody}function tick(){var rem=sr();var prog=(WINDOW-rem)/WINDOW;var cd=document.querySelector("[data-ticket-countdown]");if(cd)cd.textContent=cfg.labels.refreshInTemplate.replace("__SEC__",String(rem));var ring=document.querySelector("[data-ticket-ring=progress]");if(ring)ring.setAttribute("stroke-dashoffset",String(C*(1-prog)));var node=document.querySelector("[data-ticket-qr-payload] p");var p=payloadFor(cw());if(node&&p)node.textContent=p;var offline=!navigator.onLine;var cache=read();var expired=offline&&(!cache||cw()>cache.last_window)&&!p;setOffline(offline,expired);if(rem<=1&&navigator.onLine)location.reload()}if(cfg.horizon)write({ticket_id:cfg.horizon.ticket_id,from_window:cfg.horizon.from_window,last_window:cfg.horizon.last_window,pin:cfg.horizon.pin,entries:cfg.horizon.entries,cached_at:new Date().toISOString()});tick();setInterval(tick,1000);window.addEventListener("online",tick);window.addEventListener("offline",tick)})();`,
          }}
        />
      ) : null}
    </section>
  );
}
