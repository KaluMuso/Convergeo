import { formatK } from "@vergeo/i18n";

import { asRecord, attrBool, attrNumber, attrString } from "../../_lib/archetypes";

import {
  Chip,
  commonFacts,
  EmptyOffers,
  FactStrip,
  OfferPhoto,
  OfferPrice,
  PolicyNote,
  SectionHeading,
  SelectButton,
  type LayoutProps,
} from "./shared";

type Spec = { label: string; value: string };

export function parseSpecs(value: unknown): Spec[] {
  if (!Array.isArray(value)) return [];
  const out: Spec[] = [];
  for (const raw of value) {
    const row = asRecord(raw);
    const label = attrString(row, "label");
    const spec = attrString(row, "value");
    if (label && spec) out.push({ label, value: spec });
  }
  return out;
}

/** Equipment / vehicles / party items: item cards with spec chips and an honest deposit line. */
export function RentalLayout({ offers, attrs, t }: LayoutProps) {
  const pickup = attrString(attrs, "pickup_note");
  return (
    <>
      <FactStrip
        items={[
          ...(pickup ? [{ label: t("rental.pickup"), value: pickup }] : []),
          ...commonFacts(attrs, t),
        ]}
        testId="rental-facts"
      />
      <PolicyNote attrs={attrs} />
      <section className="flex flex-col gap-3" aria-labelledby="items-heading" data-testid="items">
        <SectionHeading id="items-heading">{t("rental.heading")}</SectionHeading>
        {offers.length === 0 ? <EmptyOffers t={t} /> : null}
        <ul className="m-0 grid list-none gap-4 p-0 sm:grid-cols-2">
          {offers.map((item) => {
            const a = asRecord(item.attributes);
            const unit = attrString(a, "unit") ?? "day";
            const deposit = attrNumber(a, "deposit_ngwee");
            const qty = attrNumber(a, "quantity_available");
            const minPeriod = attrNumber(a, "min_period");
            return (
              <li
                key={item.id}
                className="flex flex-col overflow-hidden rounded-lg border border-border bg-surface shadow-1"
                data-testid={`rental-${item.id}`}
              >
                <OfferPhoto offer={item} alt={item.name} />
                <div className="flex flex-1 flex-col gap-3 p-4">
                  <h3 className="m-0 font-semibold text-text">{item.name}</h3>
                  {item.description ? (
                    <p className="m-0 text-sm text-text-2">{item.description}</p>
                  ) : null}
                  <div className="flex flex-wrap gap-1.5">
                    {parseSpecs(a.specs).map((spec) => (
                      <Chip key={spec.label}>
                        {spec.label}: {spec.value}
                      </Chip>
                    ))}
                    {attrBool(a, "with_operator") ? (
                      <Chip strong>{t("rental.withOperator")}</Chip>
                    ) : null}
                    {attrBool(a, "delivery_available") ? <Chip>{t("rental.delivery")}</Chip> : null}
                    {qty !== null && qty > 0 ? (
                      <Chip>{t("rental.available", { count: qty })}</Chip>
                    ) : null}
                    {minPeriod && minPeriod > 1 ? (
                      <Chip>{t(`rental.minPeriod.${unit}`, { count: minPeriod })}</Chip>
                    ) : null}
                  </div>
                  <div className="mt-auto flex flex-col gap-2">
                    <OfferPrice offer={item} unit={t(`common.per.${unit}`)} t={t} />
                    {deposit ? (
                      <p className="m-0 text-xs text-text-3" data-testid="rental-deposit">
                        {t("rental.deposit", { price: formatK(deposit) })}
                      </p>
                    ) : null}
                    <SelectButton offer={item} t={t} />
                  </div>
                </div>
              </li>
            );
          })}
        </ul>
      </section>
    </>
  );
}
