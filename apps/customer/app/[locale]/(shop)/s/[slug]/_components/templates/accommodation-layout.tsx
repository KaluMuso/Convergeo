import { attrBool, attrNumber, attrString, attrStrings } from "../../_lib/archetypes";

import {
  AmenityGrid,
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

/** Hotel / lodge / guesthouse (and monthly lets): room cards, stay policy strip, amenities. */
export function AccommodationLayout({ offers, attrs, t }: LayoutProps) {
  const facts = [
    ...(attrString(attrs, "check_in")
      ? [
          {
            label: t("accommodation.checkIn"),
            value: attrString(attrs, "check_in") as string,
          },
        ]
      : []),
    ...(attrString(attrs, "check_out")
      ? [
          {
            label: t("accommodation.checkOut"),
            value: attrString(attrs, "check_out") as string,
          },
        ]
      : []),
    ...commonFacts(attrs, t),
  ];
  return (
    <>
      <FactStrip items={facts} testId="accommodation-facts" />
      <PolicyNote attrs={attrs} />
      <section className="flex flex-col gap-3" aria-labelledby="rooms-heading" data-testid="rooms">
        <SectionHeading id="rooms-heading">{t("accommodation.heading")}</SectionHeading>
        {offers.length === 0 ? <EmptyOffers t={t} /> : null}
        <ul className="m-0 grid list-none gap-4 p-0 md:grid-cols-2">
          {offers.map((room) => {
            const a = room.attributes ?? {};
            const monthly = a.stay_kind === "monthly";
            const roomType = attrString(a, "room_type");
            const beds = attrNumber(a, "beds");
            const bedType = attrString(a, "bed_type");
            const left = attrNumber(a, "units_available");
            const minNights = attrNumber(a, "min_nights");
            return (
              <li
                key={room.id}
                className="flex flex-col overflow-hidden rounded-lg border border-border bg-surface shadow-1"
                data-testid={`room-${room.id}`}
              >
                <OfferPhoto offer={room} alt={room.name} />
                <div className="flex flex-1 flex-col gap-3 p-4">
                  <div className="flex flex-wrap items-center gap-2">
                    {roomType ? (
                      <Chip strong>{t(`accommodation.roomTypes.${roomType}`)}</Chip>
                    ) : null}
                    {left !== null && left > 0 && left <= 5 ? (
                      <Chip>{t("accommodation.unitsLeft", { count: left })}</Chip>
                    ) : null}
                  </div>
                  <h3 className="m-0 font-semibold text-text">{room.name}</h3>
                  {room.description ? (
                    <p className="m-0 text-sm text-text-2">{room.description}</p>
                  ) : null}
                  <div className="flex flex-wrap gap-1.5">
                    <Chip>
                      {t("accommodation.sleeps", {
                        count: attrNumber(a, "sleeps") ?? 2,
                      })}
                    </Chip>
                    {beds !== null ? (
                      <Chip>
                        {bedType
                          ? t("accommodation.bedsOfType", {
                              count: beds,
                              type: t(`accommodation.bedTypes.${bedType}`),
                            })
                          : t("accommodation.beds", { count: beds })}
                      </Chip>
                    ) : null}
                    {attrNumber(a, "size_sqm") ? (
                      <Chip>
                        {t("accommodation.size", {
                          sqm: attrNumber(a, "size_sqm") as number,
                        })}
                      </Chip>
                    ) : null}
                    {attrBool(a, "breakfast_included") ? (
                      <Chip>{t("accommodation.breakfast")}</Chip>
                    ) : null}
                    {minNights && minNights > 1 ? (
                      <Chip>{t("accommodation.minNights", { count: minNights })}</Chip>
                    ) : null}
                    {attrStrings(a, "amenities").map((item) => (
                      <Chip key={item}>{item}</Chip>
                    ))}
                  </div>
                  <div className="mt-auto flex flex-col gap-2">
                    <OfferPrice
                      offer={room}
                      unit={monthly ? t("common.perMonth") : t("common.perNight")}
                      t={t}
                    />
                    <SelectButton offer={room} t={t} />
                  </div>
                </div>
              </li>
            );
          })}
        </ul>
      </section>
      <AmenityGrid
        id="amenities-heading"
        heading={t("accommodation.amenities")}
        items={attrStrings(attrs, "amenities")}
      />
    </>
  );
}
