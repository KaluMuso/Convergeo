import {
  sanitiseDetails,
  type ArchetypeDetails,
  type EventArchetype,
} from "@vergeo/ui/src/event-archetype";

import {
  ActivationsBlock,
  ActivitiesBlock,
  AgendaBlock,
  FaqBlock,
  GalleryBlock,
  LineupBlock,
  MenuBlock,
  NotesBlock,
  SpeakersBlock,
  SponsorBand,
  TierShowcase,
  type ShowcaseTicket,
  type T,
} from "./archetype-blocks";

import type { ReactNode } from "react";

export type ArchetypeBodyProps = {
  archetype: EventArchetype;
  /** Raw API JSON; sanitised again here (defence in depth). */
  rawDetails: unknown;
  /** Hero is images[0]; the gallery shows images[1..]. */
  images: string[];
  title: string;
  tickets: ShowcaseTicket[];
  t: T;
};

/** Sponsors belong below the header for branded events, at the end for the rest. */
export function ArchetypeLead({
  archetype,
  rawDetails,
  t,
}: Pick<ArchetypeBodyProps, "archetype" | "rawDetails" | "t">) {
  if (archetype !== "branded") return null;
  const details = sanitiseDetails(rawDetails);
  return <SponsorBand sponsors={details.sponsors} presentedBy={details.presented_by} t={t} />;
}

/** Fact chips shown on the hero: dress code and age policy. */
export function archetypeChips(details: ArchetypeDetails, t: T): string[] {
  const chips: string[] = [];
  if (details.dress_code) chips.push(t("archetype.dressCode", { value: details.dress_code }));
  if (details.age_policy) chips.push(t(`archetype.agePolicy.${details.age_policy}`));
  return chips;
}

/**
 * Archetype-specific main-column blocks, in the order that suits each template.
 * Every block renders nothing without data, so a bare event is the generic page.
 * Purchase stays in `TicketPicker`; `TierShowcase` is read-only presentation.
 */
export function ArchetypeBody({
  archetype,
  rawDetails,
  images,
  title,
  tickets,
  t,
}: ArchetypeBodyProps) {
  const d = sanitiseDetails(rawDetails);
  const gallery = images.slice(1);
  const showcase =
    tickets.length >= 2 || (archetype === "religious" && Boolean(d.donation_note)) ? (
      <TierShowcase
        tickets={tickets}
        highlightTop={archetype === "concert" || archetype === "branded"}
        donationNote={archetype === "religious" ? d.donation_note : undefined}
        t={t}
      />
    ) : null;
  const sponsors = archetype === "branded" ? null : <SponsorBand sponsors={d.sponsors} t={t} />;
  const faqs = <FaqBlock faqs={d.faqs} t={t} />;
  const galleryBlock = <GalleryBlock images={gallery} title={title} t={t} />;

  let blocks: ReactNode[];
  switch (archetype) {
    case "concert":
      blocks = [
        <LineupBlock
          key="lineup"
          lineup={d.lineup}
          stages={d.stages}
          doorsOpen={d.doors_open}
          merchNote={d.merch_note}
          t={t}
        />,
        showcase,
        galleryBlock,
        sponsors,
        faqs,
      ];
      break;
    case "religious":
      blocks = [
        <AgendaBlock key="agenda" items={d.agenda} t={t} headingKey="archetype.sections.service" />,
        <SpeakersBlock key="speakers" people={d.speakers} t={t} />,
        <NotesBlock
          key="notes"
          t={t}
          entries={[
            {
              key: "denomination",
              label: t("archetype.denomination"),
              value: d.denomination ?? "",
            },
            {
              key: "languages",
              label: t("archetype.languages"),
              value: d.languages.join(", "),
            },
            {
              key: "livestream",
              label: t("archetype.livestream"),
              value: d.livestream_url ? t("archetype.watchLivestream") : "",
              href: d.livestream_url,
            },
          ]}
        />,
        showcase,
        galleryBlock,
        sponsors,
        faqs,
      ];
      break;
    case "sports_family":
      blocks = [
        <ActivitiesBlock
          key="activities"
          activities={d.activities}
          ageGroups={d.age_groups}
          bringList={d.bring_list}
          bundleNote={d.family_bundle_note}
          t={t}
        />,
        showcase,
        galleryBlock,
        sponsors,
        faqs,
      ];
      break;
    case "restaurant":
      blocks = [
        <MenuBlock
          key="menu"
          sections={d.menu_sections}
          seatingNote={d.seating_note}
          reservationNote={d.reservation_note}
          hostName={d.host_name}
          t={t}
        />,
        showcase,
        galleryBlock,
        sponsors,
        faqs,
      ];
      break;
    case "branded":
      blocks = [
        <ActivationsBlock
          key="activations"
          activations={d.activations}
          promoNote={d.promo_note}
          giveawayNote={d.giveaway_note}
          t={t}
        />,
        showcase,
        galleryBlock,
        sponsors,
        faqs,
      ];
      break;
    case "private_gathering":
      blocks = [
        <NotesBlock
          key="notes"
          t={t}
          entries={[
            {
              key: "host",
              label: t("archetype.hostNames"),
              value: d.host_names ?? "",
            },
            {
              key: "occasion",
              label: t("archetype.occasion"),
              value: d.occasion ?? "",
            },
            {
              key: "rsvp",
              label: t("archetype.rsvp"),
              value: d.rsvp_note ?? "",
            },
            {
              key: "gift",
              label: t("archetype.gift"),
              value: d.gift_note ?? "",
            },
          ]}
        />,
        <AgendaBlock key="agenda" items={d.agenda} t={t} />,
        galleryBlock,
        showcase,
        faqs,
      ];
      break;
    default:
      blocks = [
        <AgendaBlock key="agenda" items={d.agenda} t={t} />,
        showcase,
        galleryBlock,
        sponsors,
        faqs,
      ];
  }

  return (
    <>
      {blocks.map((block, index) => (
        <div key={index} className="contents">
          {block}
        </div>
      ))}
    </>
  );
}
