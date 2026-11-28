import { formatK } from "@vergeo/i18n";
import { CloudinaryImageStatic } from "@vergeo/ui/src/media/cloudinary-image-static";

import { attrString, type Attributes } from "../../_lib/archetypes";
import { asRecord, parseAvailability } from "../../_lib/archetypes";

import { SelectOfferButton } from "./select-offer-button";

import type { ServicePackage } from "../service-packages-model";
import type { ReactNode } from "react";

/** Translator scoped to `services.templates`. */
export type T = (key: string, values?: Record<string, string | number>) => string;

export type LayoutProps = {
  offers: ServicePackage[];
  attrs: Attributes;
  t: T;
};

export function Chip({ children, strong = false }: { children: ReactNode; strong?: boolean }) {
  return (
    <span
      className={`inline-flex min-h-7 items-center rounded-pill border px-2.5 text-xs font-medium ${
        strong
          ? "border-transparent bg-[var(--vibe-strong)] text-text"
          : "border-border bg-surface text-text-2"
      }`}
    >
      {children}
    </span>
  );
}

export function SectionHeading({ id, children }: { id: string; children: ReactNode }) {
  return (
    <h2 id={id} className="font-display text-h2 text-display-ink">
      {children}
    </h2>
  );
}

/** Money for an offer: integer ngwee via `formatK`, or the "ask" label for quote-only. */
export function OfferPrice({
  offer,
  unit,
  from = false,
  t,
}: {
  offer: ServicePackage;
  unit?: string;
  from?: boolean;
  t: T;
}) {
  if (offer.price_ngwee === null) {
    return (
      <p className="m-0 font-display text-h3 text-display-ink" data-testid="offer-price">
        {t("common.priceQuote")}
      </p>
    );
  }
  return (
    <p className="m-0 font-display text-h3 text-display-ink" data-testid="offer-price">
      {from ? (
        <span className="mr-1 text-sm font-medium text-text-3">{t("common.from")}</span>
      ) : null}
      {formatK(offer.price_ngwee)}
      {unit ? <span className="ml-1 text-sm font-medium text-text-3">{unit}</span> : null}
    </p>
  );
}

export function OfferPhoto({
  offer,
  alt,
  ratio = "4/3",
}: {
  offer: ServicePackage;
  alt: string;
  ratio?: "4/3" | "16/9" | "1/1";
}) {
  const image = attrString(offer.attributes ?? {}, "image");
  if (!image) return null;
  return (
    <CloudinaryImageStatic
      publicId={image}
      alt={alt}
      width={480}
      ratio={ratio}
      sizes="(max-width: 640px) 90vw, 360px"
      className="w-full rounded-none"
    />
  );
}

export function SelectButton({ offer, t }: { offer: ServicePackage; t: T }) {
  return <SelectOfferButton offerId={offer.id} label={t("common.select")} />;
}

/** Amenities / facilities: coloured tiles from the archetype vibe. */
export function AmenityGrid({
  items,
  heading,
  id,
}: {
  items: string[];
  heading: string;
  id: string;
}) {
  if (items.length === 0) return null;
  return (
    <section className="flex flex-col gap-3" aria-labelledby={id} data-testid="amenity-grid">
      <SectionHeading id={id}>{heading}</SectionHeading>
      <ul className="m-0 grid list-none grid-cols-2 gap-2 p-0 sm:grid-cols-3">
        {items.map((item) => (
          <li
            key={item}
            className="flex items-center gap-2 rounded-md bg-[var(--vibe-tint)] px-3 py-2.5 text-sm text-text"
          >
            <span aria-hidden="true" className="text-[var(--vibe)]">
              ●
            </span>
            <span>{item}</span>
          </li>
        ))}
      </ul>
    </section>
  );
}

export function FactStrip({
  items,
  testId,
}: {
  items: { label: string; value: string }[];
  testId: string;
}) {
  if (items.length === 0) return null;
  return (
    <dl
      className="m-0 grid grid-cols-2 gap-px overflow-hidden rounded-lg border border-border bg-border sm:grid-cols-4"
      data-testid={testId}
    >
      {items.map((item) => (
        <div key={item.label} className="flex flex-col gap-0.5 bg-[var(--vibe-tint)] p-3">
          <dt className="text-xs font-semibold uppercase tracking-wide text-text-3">
            {item.label}
          </dt>
          <dd className="m-0 text-sm font-semibold text-text">{item.value}</dd>
        </div>
      ))}
    </dl>
  );
}

export function EmptyOffers({ t }: { t: T }) {
  return <p className="m-0 rounded-md bg-bg-2 p-4 text-sm text-text-2">{t("common.noOffers")}</p>;
}

/** Cancellation policy + availability, shared by every bespoke layout. */
export function commonFacts(attrs: Attributes, t: T): { label: string; value: string }[] {
  const facts: { label: string; value: string }[] = [];
  const policy = asRecord(attrs.policy);
  const cancellation = attrString(policy, "cancellation");
  if (cancellation === "flexible" || cancellation === "moderate" || cancellation === "strict") {
    facts.push({
      label: t("common.cancellation"),
      value: t(`common.cancellationKinds.${cancellation}`),
    });
  }
  facts.push({
    label: t("common.availabilityLabel"),
    value: t(`common.availability.${parseAvailability(attrs)}`),
  });
  return facts;
}

export function policyNote(attrs: Attributes): string | null {
  return attrString(asRecord(attrs.policy), "note");
}

export function PolicyNote({ attrs }: { attrs: Attributes }) {
  const note = policyNote(attrs);
  return note ? <p className="m-0 text-sm text-text-2">{note}</p> : null;
}
