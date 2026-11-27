import Link from "next/link";

const TOOLS = [
  { path: "tickets", key: "ticketsCta" },
  { path: "scan", key: "scanCta" },
  { path: "dashboard", key: "salesCta" },
  { path: "roster", key: "rosterCta" },
] as const;

type EventToolLinksProps = {
  locale: string;
  eventId: string;
  /** Translator scoped to `vendor` (keys under events.list.*). */
  t: (key: string) => string;
};

/** Compact organiser tool links (tickets, door scan, sales, roster); wraps at 360px. */
export function EventToolLinks({ locale, eventId, t }: EventToolLinksProps) {
  return (
    <nav className="mt-2 flex flex-wrap gap-2" data-testid="event-tool-links">
      {TOOLS.map((tool) => (
        <Link
          key={tool.path}
          href={`/${locale}/events/${eventId}/${tool.path}`}
          className="inline-flex min-h-11 flex-1 items-center justify-center rounded-md border border-border px-3 text-sm font-medium"
        >
          {t(`events.list.${tool.key}`)}
        </Link>
      ))}
    </nav>
  );
}
