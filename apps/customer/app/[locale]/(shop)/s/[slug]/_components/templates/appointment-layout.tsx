import { attrBool, attrNumber, attrString, attrStrings, parseStaff } from "../../_lib/archetypes";

import {
  Chip,
  commonFacts,
  EmptyOffers,
  FactStrip,
  OfferPrice,
  PolicyNote,
  SectionHeading,
  SelectButton,
  type LayoutProps,
  type T,
} from "./shared";

import type { ServicePackage } from "../service-packages-model";

const UNGROUPED = "";

/** Menu sections in the vendor's order; offers without a group come first. */
export function groupMenu(offers: ServicePackage[]): { group: string; items: ServicePackage[] }[] {
  const groups = new Map<string, ServicePackage[]>();
  for (const offer of offers) {
    const group = attrString(offer.attributes ?? {}, "group") ?? UNGROUPED;
    groups.set(group, [...(groups.get(group) ?? []), offer]);
  }
  return [...groups.entries()]
    .sort(([a], [b]) => (a === UNGROUPED ? -1 : b === UNGROUPED ? 1 : 0))
    .map(([group, items]) => ({ group, items }));
}

function durationLabel(minutes: number, t: T): string {
  if (minutes < 60) return t("appointment.minutes", { count: minutes });
  const hours = Math.floor(minutes / 60);
  const rest = minutes % 60;
  return rest === 0
    ? t("appointment.hours", { count: hours })
    : t("appointment.hoursMinutes", { hours, minutes: rest });
}

/** Salon / barber / tailor / garage: a treatment menu with durations, then the stylists. */
export function AppointmentLayout({ offers, attrs, t }: LayoutProps) {
  const staff = parseStaff(attrs);
  const menu = groupMenu(offers);
  return (
    <>
      <FactStrip
        items={[
          ...commonFacts(attrs, t),
          ...(attrBool(attrs, "walk_ins")
            ? [
                {
                  label: t("appointment.walkIns"),
                  value: t("appointment.walkInsYes"),
                },
              ]
            : []),
        ]}
        testId="appointment-facts"
      />
      <PolicyNote attrs={attrs} />
      <section className="flex flex-col gap-4" aria-labelledby="menu-heading" data-testid="menu">
        <SectionHeading id="menu-heading">{t("appointment.heading")}</SectionHeading>
        {offers.length === 0 ? <EmptyOffers t={t} /> : null}
        {menu.map(({ group, items }) => (
          <div key={group || "ungrouped"} className="flex flex-col gap-2">
            {group ? (
              <h3 className="m-0 text-sm font-semibold uppercase tracking-wide text-[var(--vibe)]">
                {group}
              </h3>
            ) : null}
            <ul className="m-0 flex list-none flex-col gap-2 p-0">
              {items.map((item) => {
                const a = item.attributes ?? {};
                const minutes = attrNumber(a, "duration_min");
                return (
                  <li
                    key={item.id}
                    className="grid gap-3 rounded-lg border border-border bg-surface p-4 sm:grid-cols-[1fr_auto] sm:items-center"
                    data-testid={`treatment-${item.id}`}
                  >
                    <div className="flex flex-col gap-1.5">
                      <h4 className="m-0 font-semibold text-text">{item.name}</h4>
                      {item.description ? (
                        <p className="m-0 text-sm text-text-2">{item.description}</p>
                      ) : null}
                      <div className="flex flex-wrap gap-1.5">
                        {minutes ? <Chip strong>{durationLabel(minutes, t)}</Chip> : null}
                        {attrBool(a, "home_visit") ? (
                          <Chip>{t("appointment.homeVisit")}</Chip>
                        ) : null}
                        {attrStrings(a, "staff").map((name) => (
                          <Chip key={name}>{name}</Chip>
                        ))}
                      </div>
                    </div>
                    <div className="flex items-center justify-between gap-3 sm:flex-col sm:items-end">
                      <OfferPrice offer={item} from={attrBool(a, "price_is_from")} t={t} />
                      <div className="w-32">
                        <SelectButton offer={item} t={t} />
                      </div>
                    </div>
                  </li>
                );
              })}
            </ul>
          </div>
        ))}
      </section>
      {staff.length > 0 ? (
        <section
          className="flex flex-col gap-3"
          aria-labelledby="staff-heading"
          data-testid="staff"
        >
          <SectionHeading id="staff-heading">{t("appointment.team")}</SectionHeading>
          <ul className="m-0 flex list-none flex-wrap gap-3 p-0">
            {staff.map((member) => (
              <li
                key={member.name}
                className="flex items-center gap-2 rounded-pill bg-[var(--vibe-tint)] py-1.5 pl-1.5 pr-4"
              >
                <span
                  aria-hidden="true"
                  className="inline-flex h-8 w-8 items-center justify-center rounded-full bg-[var(--vibe-strong)] font-display text-sm font-bold text-text"
                >
                  {member.name.charAt(0)}
                </span>
                <span className="text-sm font-semibold text-text">{member.name}</span>
                {member.role ? <span className="text-xs text-text-3">{member.role}</span> : null}
              </li>
            ))}
          </ul>
        </section>
      ) : null}
    </>
  );
}
