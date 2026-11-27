import { formatK } from "@vergeo/i18n";

import {
  attrBool,
  attrNumber,
  attrString,
  asRecord,
  parseSchedule,
  type ClassSlot,
} from "../../_lib/archetypes";

import {
  AmenityGrid,
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

/** The priced pass with the lowest cost per valid day; null when fewer than two compare. */
export function bestValueId(offers: ServicePackage[]): string | null {
  const priced = offers
    .map((offer) => {
      const days = attrNumber(offer.attributes ?? {}, "valid_days") ?? 0;
      return {
        id: offer.id,
        perDay: offer.price_ngwee && days > 0 ? offer.price_ngwee / days : null,
      };
    })
    .filter((row): row is { id: string; perDay: number } => row.perDay !== null);
  if (priced.length < 2) return null;
  return priced.reduce((best, row) => (row.perDay < best.perDay ? row : best)).id;
}

export function groupSchedule(slots: ClassSlot[]): { day: number; slots: ClassSlot[] }[] {
  const days = new Map<number, ClassSlot[]>();
  for (const slot of slots) days.set(slot.day, [...(days.get(slot.day) ?? []), slot]);
  return [...days.entries()].sort(([a], [b]) => a - b).map(([day, rows]) => ({ day, slots: rows }));
}

function Schedule({ attrs, t }: { attrs: Record<string, unknown>; t: T }) {
  const days = groupSchedule(parseSchedule(attrs));
  if (days.length === 0) return null;
  return (
    <section
      className="flex flex-col gap-3"
      aria-labelledby="schedule-heading"
      data-testid="schedule"
    >
      <SectionHeading id="schedule-heading">{t("membership.schedule")}</SectionHeading>
      <ul className="m-0 grid list-none gap-3 p-0 sm:grid-cols-2">
        {days.map(({ day, slots }) => (
          <li key={day} className="rounded-lg border border-border bg-surface p-3">
            <p className="m-0 mb-2 text-sm font-semibold text-[var(--vibe)]">{t(`days.${day}`)}</p>
            <ul className="m-0 flex list-none flex-col gap-1.5 p-0">
              {slots.map((slot) => (
                <li
                  key={`${slot.start}-${slot.title}`}
                  className="flex items-baseline justify-between gap-2 text-sm"
                >
                  <span className="text-text">
                    <span className="font-semibold">{slot.start}</span> {slot.title}
                  </span>
                  <span className="shrink-0 text-xs text-text-3">
                    {slot.capacity
                      ? t("membership.spots", { count: slot.capacity })
                      : t("appointment.minutes", { count: slot.duration_min })}
                  </span>
                </li>
              ))}
            </ul>
          </li>
        ))}
      </ul>
    </section>
  );
}

/** Gym / studio: pass cards with a best-value highlight, weekly class schedule, facilities. */
export function MembershipLayout({ offers, attrs, t }: LayoutProps) {
  const best = bestValueId(offers);
  return (
    <>
      <FactStrip items={commonFacts(attrs, t)} testId="membership-facts" />
      <PolicyNote attrs={attrs} />
      <section
        className="flex flex-col gap-3"
        aria-labelledby="passes-heading"
        data-testid="passes"
      >
        <SectionHeading id="passes-heading">{t("membership.heading")}</SectionHeading>
        {offers.length === 0 ? <EmptyOffers t={t} /> : null}
        <ul className="m-0 grid list-none gap-4 p-0 sm:grid-cols-2 lg:grid-cols-3">
          {offers.map((pass) => {
            const a = asRecord(pass.attributes);
            const kind = attrString(a, "pass_kind");
            const visits = attrNumber(a, "visits_included");
            const days = attrNumber(a, "valid_days");
            const guests = attrNumber(a, "guest_passes");
            const highlight = best === pass.id;
            return (
              <li
                key={pass.id}
                className={`flex flex-col gap-3 rounded-lg border p-4 shadow-1 ${
                  highlight
                    ? "border-[var(--vibe)] bg-[var(--vibe-tint)]"
                    : "border-border bg-surface"
                }`}
                data-testid={`pass-${pass.id}`}
              >
                <div className="flex flex-wrap items-center gap-2">
                  {kind ? <Chip strong>{t(`membership.kinds.${kind}`)}</Chip> : null}
                  {highlight ? <Chip strong>{t("membership.bestValue")}</Chip> : null}
                </div>
                <h3 className="m-0 font-semibold text-text">{pass.name}</h3>
                <OfferPrice offer={pass} t={t} />
                {pass.price_ngwee && days ? (
                  <p className="m-0 text-xs text-text-3">
                    {t("membership.perDay", {
                      price: formatK(Math.round(pass.price_ngwee / days)),
                    })}
                  </p>
                ) : null}
                {pass.description ? (
                  <p className="m-0 text-sm text-text-2">{pass.description}</p>
                ) : null}
                <ul className="m-0 flex list-none flex-col gap-1 p-0 text-sm text-text-2">
                  {days ? <li>{t("membership.validFor", { count: days })}</li> : null}
                  <li>
                    {visits ? t("membership.visits", { count: visits }) : t("membership.unlimited")}
                  </li>
                  {attrBool(a, "classes_included") ? <li>{t("membership.classes")}</li> : null}
                  {guests ? <li>{t("membership.guests", { count: guests })}</li> : null}
                  {attrBool(a, "peak_hours_only") ? <li>{t("membership.peakOnly")}</li> : null}
                </ul>
                <div className="mt-auto">
                  <SelectButton offer={pass} t={t} />
                </div>
              </li>
            );
          })}
        </ul>
      </section>
      <Schedule attrs={attrs} t={t} />
      <AmenityGrid
        id="facilities-heading"
        heading={t("membership.facilities")}
        items={
          Array.isArray(attrs.amenities)
            ? (attrs.amenities as unknown[]).filter((x): x is string => typeof x === "string")
            : []
        }
      />
    </>
  );
}
