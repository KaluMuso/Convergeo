import { loadNamespace, LOCALES, type Locale } from "@vergeo/i18n";
import Link from "next/link";
import { createTranslator, type AbstractIntlMessages } from "next-intl";
import { getMessages, setRequestLocale } from "next-intl/server";

import { getAccountAccessToken } from "../_components/account-server";

import type { Metadata } from "next";

export const metadata: Metadata = {
  robots: {
    index: false,
    follow: false,
  },
};

type PageProps = {
  params: Promise<{ locale: string }>;
};

type WalletTicketSummary = {
  id: string;
  status: string;
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

function getApiBaseUrl(): string {
  return process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";
}

async function fetchWalletTickets(accessToken: string): Promise<WalletTicketSummary[]> {
  const response = await fetch(`${getApiBaseUrl()}/account/tickets`, {
    headers: {
      Authorization: `Bearer ${accessToken}`,
      Accept: "application/json",
    },
    cache: "no-store",
  });
  if (!response.ok) {
    return [];
  }
  const body = (await response.json()) as { tickets?: WalletTicketSummary[] };
  return body.tickets ?? [];
}

export function generateStaticParams() {
  return LOCALES.map((locale) => ({ locale }));
}

export default async function AccountTicketsPage({ params }: PageProps) {
  const { locale } = await params;

  if (!LOCALES.includes(locale as Locale)) {
    return null;
  }

  setRequestLocale(locale);
  const accessToken = await getAccountAccessToken(locale);
  const baseMessages = await getMessages();
  const eventsMessages = await loadNamespace(locale as Locale, "events");
  const messages = { ...baseMessages, events: eventsMessages } as AbstractIntlMessages;
  const t = createTranslator({ locale, messages, namespace: "events.wallet" }) as (
    key: string,
    values?: Record<string, string | number>,
  ) => string;

  const tickets = await fetchWalletTickets(accessToken);

  if (tickets.length === 0) {
    return (
      <section className="space-y-4 rounded border border-border bg-surface p-6 text-center">
        <h2 className="font-display text-h2 text-display-ink">{t("emptyTitle")}</h2>
        <p className="text-sm text-text-2">{t("emptyBody")}</p>
        <Link
          href={`/${locale}/events`}
          className="inline-flex min-h-11 items-center justify-center rounded bg-primary px-5 text-sm font-medium text-surface"
        >
          {t("emptyCta")}
        </Link>
      </section>
    );
  }

  return (
    <section className="space-y-6">
      <header className="space-y-1">
        <h2 className="font-display text-h2 text-display-ink">{t("title")}</h2>
      </header>

      <ul className="space-y-3">
        {tickets.map((ticket) => {
          const startsAt = new Date(ticket.instance.starts_at).toLocaleString(locale, {
            dateStyle: "medium",
            timeStyle: "short",
          });
          const statusKey = ticket.status as "issued" | "checked_in" | "transferred" | "void";

          return (
            <li
              key={ticket.id}
              className="flex flex-col gap-3 rounded border border-border bg-surface p-4 sm:flex-row sm:items-center sm:justify-between"
            >
              <div className="min-w-0 space-y-1">
                <p className="text-sm font-medium text-display-ink">{ticket.event.title}</p>
                <p className="text-xs text-text-2">
                  {ticket.ticket_type.name}
                  {ticket.event.venue ? ` · ${ticket.event.venue}` : ""}
                </p>
                <p className="text-xs text-text-2">{t("list.startsAt", { datetime: startsAt })}</p>
                <p className="text-xs font-medium text-primary">{t(`list.status.${statusKey}`)}</p>
              </div>
              <Link
                href={`/${locale}/account/tickets/${ticket.id}`}
                className="inline-flex min-h-11 shrink-0 items-center justify-center rounded border border-primary px-4 text-sm font-medium text-primary"
              >
                {t("list.viewTicket")}
              </Link>
            </li>
          );
        })}
      </ul>
    </section>
  );
}
