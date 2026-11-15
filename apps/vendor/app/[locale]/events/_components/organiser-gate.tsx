"use client";

import Link from "next/link";
import { useTranslations } from "next-intl";

type OrganiserGateProps = {
  locale: string;
  /** `events_collaboration` flag (read from the API; false keeps the coming-soon stub). */
  collaborationEnabled?: boolean;
};

/**
 * Shown instead of "Could not load events" when the account is not an
 * organiser. Two honest paths: become one (verify your ID) or run an event
 * with a verified organiser (live when the `events_collaboration` flag is on).
 */
export function OrganiserGate({ locale, collaborationEnabled = false }: OrganiserGateProps) {
  const t = useTranslations("vendor");

  return (
    <section
      className="flex flex-col gap-3"
      data-testid="organiser-gate"
      aria-labelledby="organiser-gate-title"
    >
      <header className="flex flex-col gap-1">
        <h1 id="organiser-gate-title" className="text-xl font-semibold text-text">
          {t("events.gate.title")}
        </h1>
        <p className="text-sm text-text-2">{t("events.gate.intro")}</p>
      </header>

      <div className="flex flex-col gap-2 rounded-lg border border-border bg-surface p-4">
        <h2 className="text-base font-semibold text-text">{t("events.gate.become.title")}</h2>
        <p className="text-sm text-text-2">{t("events.gate.become.body")}</p>
        <Link
          href={`/${locale}/onboarding/status`}
          data-testid="organiser-gate-become"
          className="inline-flex min-h-11 items-center justify-center rounded-md bg-primary px-4 text-sm font-medium text-surface"
        >
          {t("events.gate.become.cta")}
        </Link>
      </div>

      <div className="flex flex-col gap-2 rounded-lg border border-border bg-surface p-4">
        <h2 className="text-base font-semibold text-text">{t("events.gate.collaborate.title")}</h2>
        <p className="text-sm text-text-2">{t("events.gate.collaborate.body")}</p>
        {collaborationEnabled ? (
          <Link
            href={`/${locale}/events/collaborate`}
            data-testid="organiser-gate-collaborate"
            className="inline-flex min-h-11 items-center justify-center rounded-md border border-primary px-4 text-sm font-medium text-primary"
          >
            {t("events.gate.collaborate.open")}
          </Link>
        ) : (
          <>
            <button
              type="button"
              disabled
              aria-disabled="true"
              data-testid="organiser-gate-collaborate"
              className="inline-flex min-h-11 items-center justify-center rounded-md border border-border px-4 text-sm font-medium text-text-3"
            >
              {t("events.gate.collaborate.cta")}
            </button>
            <p className="text-xs text-text-3">{t("events.gate.collaborate.soon")}</p>
          </>
        )}
      </div>
    </section>
  );
}
