import { formatK } from "@vergeo/i18n";
import {
  classifyTicketTier,
  type ArchetypeDetails,
  type Sponsor,
  type TicketTierKind,
} from "@vergeo/ui/src/event-archetype";
import { CloudinaryImageStatic } from "@vergeo/ui/src/media/cloudinary-image-static";
import Link from "next/link";

import { ExternalUrlImage } from "../../../../../../../lib/media/external-url-image";
import { splitTicketPerks, tierSpotsRemaining } from "../../_lib/tier-availability";

/** Server-component translator shape shared with the event page. */
export type T = (key: string, values?: Record<string, string | number>) => string;

const sectionClass = "flex flex-col gap-3";
const headingClass = "font-display text-h2 text-display-ink";
const cardClass = "rounded-lg border border-border bg-surface p-4 shadow-1";

/** Cloudinary public id or https URL (already sanitised upstream). */
export function ArchImage({
  src,
  alt,
  width,
  ratio,
  className,
}: {
  src: string;
  alt: string;
  width: number;
  ratio: `${number}/${number}`;
  className?: string;
}) {
  if (src.startsWith("https://")) {
    return (
      <ExternalUrlImage
        src={src}
        alt={alt}
        width={width}
        height={Math.round((width * Number(ratio.split("/")[1])) / Number(ratio.split("/")[0]))}
        className={className}
      />
    );
  }
  return (
    <CloudinaryImageStatic
      publicId={src}
      alt={alt}
      width={width}
      ratio={ratio}
      className={className}
    />
  );
}

function Heading({ id, children }: { id: string; children: string }) {
  return (
    <h2 id={id} className={headingClass}>
      {children}
    </h2>
  );
}

// --- Agenda / order of service ---------------------------------------------

export function AgendaBlock({
  items,
  t,
  headingKey = "archetype.sections.agenda",
}: {
  items: ArchetypeDetails["agenda"];
  t: T;
  headingKey?: string;
}) {
  if (items.length === 0) return null;
  return (
    <section className={sectionClass} aria-labelledby="arch-agenda" data-testid="block-agenda">
      <Heading id="arch-agenda">{t(headingKey)}</Heading>
      <ol className="flex list-none flex-col gap-2 p-0">
        {items.map((item, index) => (
          <li key={`${item.time}-${index}`} className={`${cardClass} flex gap-4`}>
            <span className="w-14 shrink-0 font-display text-h3 text-primary">{item.time}</span>
            <div className="min-w-0">
              <p className="font-medium text-text">{item.title}</p>
              {item.speaker ? <p className="text-sm text-text-2">{item.speaker}</p> : null}
              {item.notes ? <p className="mt-1 text-sm text-text-3">{item.notes}</p> : null}
            </div>
          </li>
        ))}
      </ol>
    </section>
  );
}

// --- Speakers / hosts -------------------------------------------------------

export function SpeakersBlock({ people, t }: { people: ArchetypeDetails["speakers"]; t: T }) {
  if (people.length === 0) return null;
  return (
    <section className={sectionClass} aria-labelledby="arch-speakers" data-testid="block-speakers">
      <Heading id="arch-speakers">{t("archetype.sections.speakers")}</Heading>
      <ul className="grid list-none grid-cols-1 gap-3 p-0 sm:grid-cols-2">
        {people.map((person) => (
          <li key={person.name} className={`${cardClass} flex items-start gap-3`}>
            {person.image ? (
              <div className="h-14 w-14 shrink-0 overflow-hidden rounded-full border border-border">
                <ArchImage
                  src={person.image}
                  alt=""
                  width={112}
                  ratio="1/1"
                  className="h-full w-full object-cover"
                />
              </div>
            ) : null}
            <div className="min-w-0">
              <p className="font-medium text-text">{person.name}</p>
              {person.role ? <p className="text-sm text-text-2">{person.role}</p> : null}
              {person.bio ? <p className="mt-1 text-sm text-text-3">{person.bio}</p> : null}
            </div>
          </li>
        ))}
      </ul>
    </section>
  );
}

// --- Concert lineup ----------------------------------------------------------

export function LineupBlock({
  lineup,
  stages,
  doorsOpen,
  merchNote,
  t,
}: {
  lineup: ArchetypeDetails["lineup"];
  stages: string[];
  doorsOpen?: string;
  merchNote?: string;
  t: T;
}) {
  if (lineup.length === 0 && !doorsOpen && !merchNote) return null;
  const headliners = lineup.filter((act) => act.role === "headliner");
  const rest = lineup.filter((act) => act.role !== "headliner");
  return (
    <section className={sectionClass} aria-labelledby="arch-lineup" data-testid="block-lineup">
      <Heading id="arch-lineup">{t("archetype.sections.lineup")}</Heading>
      {doorsOpen ? (
        <p className="text-sm font-semibold text-text-2">
          {t("archetype.doorsOpen", { time: doorsOpen })}
        </p>
      ) : null}
      {headliners.length > 0 ? (
        <ul className="grid list-none grid-cols-1 gap-3 p-0 sm:grid-cols-2">
          {headliners.map((act) => (
            <li
              key={act.name}
              className="overflow-hidden rounded-lg border-2 bg-panel text-panel-text shadow-2"
              style={{ borderColor: "var(--arch-accent)" }}
            >
              {act.image ? (
                <ArchImage
                  src={act.image}
                  alt={act.name}
                  width={640}
                  ratio="4/3"
                  className="w-full object-cover"
                />
              ) : null}
              <div className="p-4">
                <p className="text-xs font-semibold uppercase tracking-[0.14em] text-panel-muted">
                  {t("archetype.roles.headliner")}
                </p>
                <p className="font-display text-h2">{act.name}</p>
                {act.slot ? <p className="text-sm text-panel-muted">{act.slot}</p> : null}
                {act.bio ? <p className="mt-1 text-sm text-panel-muted">{act.bio}</p> : null}
              </div>
            </li>
          ))}
        </ul>
      ) : null}
      {rest.length > 0 ? (
        <ul className="flex list-none flex-col gap-2 p-0">
          {rest.map((act) => (
            <li key={act.name} className={`${cardClass} flex items-center gap-3`}>
              <span className="w-14 shrink-0 font-display text-h3 text-primary">
                {act.slot ?? "–"}
              </span>
              <div className="min-w-0">
                <p className="font-medium text-text">{act.name}</p>
                <p className="text-sm text-text-2">
                  {t(`archetype.roles.${act.role}`)}
                  {act.stage && stages.length > 0
                    ? ` · ${t("archetype.stage", { name: act.stage })}`
                    : act.stage
                      ? ` · ${act.stage}`
                      : ""}
                </p>
              </div>
            </li>
          ))}
        </ul>
      ) : null}
      {merchNote ? (
        <p
          className="rounded-lg p-4 text-sm text-text-2"
          style={{ background: "var(--arch-tint)" }}
        >
          <span className="font-semibold text-text">{t("archetype.merch")}: </span>
          {merchNote}
        </p>
      ) : null}
    </section>
  );
}

// --- Sports / family ---------------------------------------------------------

export function ActivitiesBlock({
  activities,
  ageGroups,
  bringList,
  bundleNote,
  t,
}: {
  activities: ArchetypeDetails["activities"];
  ageGroups: ArchetypeDetails["age_groups"];
  bringList: string[];
  bundleNote?: string;
  t: T;
}) {
  if (!activities.length && !ageGroups.length && !bringList.length && !bundleNote) return null;
  return (
    <section
      className={sectionClass}
      aria-labelledby="arch-activities"
      data-testid="block-activities"
    >
      <Heading id="arch-activities">{t("archetype.sections.activities")}</Heading>
      {activities.length > 0 ? (
        <ul className="grid list-none grid-cols-1 gap-3 p-0 sm:grid-cols-2">
          {activities.map((activity, index) => (
            <li key={`${activity.name}-${index}`} className={cardClass}>
              <p className="font-medium text-text">{activity.name}</p>
              <p className="text-sm text-text-2">
                {[activity.time, activity.area, activity.age_group].filter(Boolean).join(" · ")}
              </p>
            </li>
          ))}
        </ul>
      ) : null}
      {ageGroups.length > 0 ? (
        <div className="rounded-lg p-4" style={{ background: "var(--arch-tint)" }}>
          <h3 className="font-display text-h3 text-display-ink">
            {t("archetype.sections.ageGroups")}
          </h3>
          <ul className="mt-2 flex list-none flex-wrap gap-2 p-0">
            {ageGroups.map((group) => (
              <li
                key={group.label}
                className="rounded-full border border-border bg-surface px-3 py-1 text-sm text-text"
              >
                {group.label} ·{" "}
                {group.max_age !== undefined
                  ? t("archetype.ageRange", {
                      min: group.min_age,
                      max: group.max_age,
                    })
                  : t("archetype.agePlus", { min: group.min_age })}
              </li>
            ))}
          </ul>
        </div>
      ) : null}
      {bundleNote ? (
        <p className="text-sm text-text-2">
          <span className="font-semibold text-text">{t("archetype.familyBundle")}: </span>
          {bundleNote}
        </p>
      ) : null}
      {bringList.length > 0 ? (
        <div>
          <h3 className="font-display text-h3 text-display-ink">{t("archetype.bringList")}</h3>
          <ul className="mt-1 list-disc pl-5 text-sm text-text-2">
            {bringList.map((item) => (
              <li key={item}>{item}</li>
            ))}
          </ul>
        </div>
      ) : null}
    </section>
  );
}

// --- Restaurant menu ---------------------------------------------------------

export function MenuBlock({
  sections,
  seatingNote,
  reservationNote,
  hostName,
  t,
}: {
  sections: ArchetypeDetails["menu_sections"];
  seatingNote?: string;
  reservationNote?: string;
  hostName?: string;
  t: T;
}) {
  if (!sections.length && !seatingNote && !reservationNote && !hostName) return null;
  return (
    <section className={sectionClass} aria-labelledby="arch-menu" data-testid="block-menu">
      <Heading id="arch-menu">{t("archetype.sections.menu")}</Heading>
      {hostName ? (
        <p className="text-sm text-text-2">{t("archetype.hostedBy", { name: hostName })}</p>
      ) : null}
      {sections.map((section) => (
        <div key={section.title} className={cardClass}>
          <h3 className="font-display text-h3 text-display-ink">{section.title}</h3>
          <ul className="mt-2 flex list-none flex-col gap-3 p-0">
            {section.items.map((item) => (
              <li key={item.name} className="flex items-start justify-between gap-3">
                <div className="min-w-0">
                  <p className="font-medium text-text">{item.name}</p>
                  {item.description ? (
                    <p className="text-sm text-text-2">{item.description}</p>
                  ) : null}
                  {item.dietary.length > 0 ? (
                    <p className="text-xs text-text-3">
                      {item.dietary.map((tag) => t(`archetype.dietary.${tag}`)).join(" · ")}
                    </p>
                  ) : null}
                </div>
                {item.price_ngwee !== undefined ? (
                  <span className="shrink-0 text-sm font-semibold text-price">
                    {formatK(item.price_ngwee)}
                  </span>
                ) : null}
              </li>
            ))}
          </ul>
        </div>
      ))}
      {seatingNote ? (
        <p className="text-sm text-text-2">
          <span className="font-semibold text-text">{t("archetype.seating")}: </span>
          {seatingNote}
        </p>
      ) : null}
      {reservationNote ? (
        <p className="text-sm text-text-2">
          <span className="font-semibold text-text">{t("archetype.reservation")}: </span>
          {reservationNote}
        </p>
      ) : null}
    </section>
  );
}

// --- Branded activations -----------------------------------------------------

export function ActivationsBlock({
  activations,
  promoNote,
  giveawayNote,
  t,
}: {
  activations: ArchetypeDetails["activations"];
  promoNote?: string;
  giveawayNote?: string;
  t: T;
}) {
  if (!activations.length && !promoNote && !giveawayNote) return null;
  return (
    <section
      className={sectionClass}
      aria-labelledby="arch-activations"
      data-testid="block-activations"
    >
      <Heading id="arch-activations">{t("archetype.sections.activations")}</Heading>
      {activations.length > 0 ? (
        <ul className="grid list-none grid-cols-1 gap-3 p-0 sm:grid-cols-2">
          {activations.map((activation) => (
            <li key={activation.title} className={cardClass}>
              <p className="font-medium text-text">{activation.title}</p>
              {activation.description ? (
                <p className="text-sm text-text-2">{activation.description}</p>
              ) : null}
            </li>
          ))}
        </ul>
      ) : null}
      {promoNote ? <p className="text-sm text-text-2">{promoNote}</p> : null}
      {giveawayNote ? <p className="text-sm text-text-2">{giveawayNote}</p> : null}
    </section>
  );
}

// --- Religious extras / private gathering notes -------------------------------

export function NotesBlock({
  entries,
  t,
}: {
  entries: { key: string; label: string; value: string; href?: string }[];
  t: T;
}) {
  const visible = entries.filter((entry) => entry.value);
  if (visible.length === 0) return null;
  return (
    <section className={sectionClass} aria-labelledby="arch-notes" data-testid="block-notes">
      <Heading id="arch-notes">{t("archetype.sections.notes")}</Heading>
      <dl className="flex flex-col gap-3">
        {visible.map((entry) => (
          <div
            key={entry.key}
            className="rounded-lg p-4"
            style={{ background: "var(--arch-tint)" }}
          >
            <dt className="text-xs font-semibold uppercase tracking-[0.12em] text-text-3">
              {entry.label}
            </dt>
            <dd className="mt-1 text-sm text-text">
              {entry.href ? (
                <Link
                  href={entry.href}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="font-semibold text-primary underline-offset-4 hover:underline"
                >
                  {entry.value}
                </Link>
              ) : (
                entry.value
              )}
            </dd>
          </div>
        ))}
      </dl>
    </section>
  );
}

// --- Sponsor band ---------------------------------------------------------------

export function SponsorBand({
  sponsors,
  presentedBy,
  t,
}: {
  sponsors: Sponsor[];
  presentedBy?: Sponsor;
  t: T;
}) {
  const others = sponsors.filter((s) => s.name !== presentedBy?.name);
  if (!presentedBy && others.length === 0) return null;
  return (
    <section
      className="flex flex-col gap-3 rounded-lg border border-border p-4"
      style={{ background: "var(--arch-tint)" }}
      aria-labelledby="arch-sponsors"
      data-testid="sponsor-band"
    >
      <h2
        id="arch-sponsors"
        className="text-xs font-semibold uppercase tracking-[0.14em] text-text-3"
      >
        {presentedBy ? t("archetype.presentedBy") : t("archetype.sections.sponsors")}
      </h2>
      {presentedBy ? <SponsorChip sponsor={presentedBy} t={t} large /> : null}
      {others.length > 0 ? (
        <ul className="flex list-none flex-wrap items-center gap-3 p-0">
          {others.map((sponsor) => (
            <li key={sponsor.name}>
              <SponsorChip sponsor={sponsor} t={t} />
            </li>
          ))}
        </ul>
      ) : null}
    </section>
  );
}

function SponsorChip({ sponsor, t, large }: { sponsor: Sponsor; t: T; large?: boolean }) {
  const inner = (
    <span className="flex items-center gap-3">
      {sponsor.logo ? (
        <span
          className={`${large ? "h-14 w-14" : "h-10 w-10"} shrink-0 overflow-hidden rounded-full border border-border bg-surface`}
        >
          <ArchImage
            src={sponsor.logo}
            alt=""
            width={large ? 112 : 80}
            ratio="1/1"
            className="h-full w-full object-contain"
          />
        </span>
      ) : null}
      <span className="min-w-0">
        <span className={`block font-semibold text-text ${large ? "font-display text-h3" : ""}`}>
          {sponsor.name}
        </span>
        {sponsor.tagline ? (
          <span className="block text-sm text-text-2">{sponsor.tagline}</span>
        ) : null}
      </span>
    </span>
  );
  if (!sponsor.link_url) return inner;
  return (
    <Link
      href={sponsor.link_url}
      target="_blank"
      rel="noopener noreferrer sponsored"
      aria-label={t("archetype.visitSponsor", { name: sponsor.name })}
      className="inline-flex min-h-11 items-center focus-visible:outline-none focus-visible:shadow-focusRing"
    >
      {inner}
    </Link>
  );
}

// --- FAQs ---------------------------------------------------------------------

export function FaqBlock({ faqs, t }: { faqs: ArchetypeDetails["faqs"]; t: T }) {
  if (faqs.length === 0) return null;
  return (
    <section className={sectionClass} aria-labelledby="arch-faqs" data-testid="block-faqs">
      <Heading id="arch-faqs">{t("archetype.sections.faqs")}</Heading>
      <div className="flex flex-col gap-2">
        {faqs.map((faq) => (
          <details key={faq.question} className={cardClass}>
            <summary className="min-h-11 cursor-pointer font-medium text-text">
              {faq.question}
            </summary>
            <p className="mt-2 text-sm text-text-2">{faq.answer}</p>
          </details>
        ))}
      </div>
    </section>
  );
}

// --- Gallery --------------------------------------------------------------------

export function GalleryBlock({ images, title, t }: { images: string[]; title: string; t: T }) {
  if (images.length === 0) return null;
  return (
    <section className={sectionClass} aria-labelledby="arch-gallery" data-testid="block-gallery">
      <Heading id="arch-gallery">{t("archetype.sections.gallery")}</Heading>
      <ul className="grid list-none grid-cols-2 gap-2 p-0 md:grid-cols-3">
        {images.map((src, index) => (
          <li
            key={src}
            className={`overflow-hidden rounded-lg ${index === 0 ? "col-span-2 md:col-span-2" : ""}`}
          >
            <ArchImage
              src={src}
              alt={t("archetype.galleryAlt", { title, n: index + 2 })}
              width={index === 0 ? 800 : 400}
              ratio={index === 0 ? "16/9" : "4/3"}
              className="h-full w-full object-cover"
            />
          </li>
        ))}
      </ul>
    </section>
  );
}

// --- Fact chips (dress code / age policy / languages) ---------------------------

export function FactChips({ chips }: { chips: string[] }) {
  if (chips.length === 0) return null;
  return (
    <ul className="flex list-none flex-wrap gap-2 p-0" data-testid="fact-chips">
      {chips.map((chip) => (
        <li
          key={chip}
          className="v-glass v-glass--overlay rounded-full px-3 py-1 text-xs font-semibold text-panel-text"
        >
          {chip}
        </li>
      ))}
    </ul>
  );
}

// --- Ticket tier showcase (read-only; purchase stays in TicketPicker) --------------

export type ShowcaseTicket = {
  id: string;
  name: string;
  price_ngwee: number;
  is_free: boolean;
  is_sold_out: boolean;
  qty_cap: number | null;
  tickets_sold: number;
  perks?: string | null;
  early_bird_price_ngwee: number | null;
};

const TIER_BADGE_KEYS: Partial<Record<TicketTierKind, string>> = {
  vvip: "archetype.tier.vvip",
  vip: "archetype.tier.vip",
  ga: "archetype.tier.ga",
  family: "archetype.tier.family",
  child: "archetype.tier.child",
  table: "archetype.tier.table",
};

export function TierShowcase({
  tickets,
  highlightTop,
  donationNote,
  t,
}: {
  tickets: ShowcaseTicket[];
  highlightTop: boolean;
  donationNote?: string;
  t: T;
}) {
  if (tickets.length === 0) return null;
  const sorted = [...tickets].sort((a, b) => a.price_ngwee - b.price_ngwee);
  const topId = highlightTop && sorted.length > 1 ? sorted[sorted.length - 1]?.id : null;
  return (
    <section className={sectionClass} aria-labelledby="arch-tiers" data-testid="tier-showcase">
      <Heading id="arch-tiers">{t("archetype.tier.heading")}</Heading>
      <ul className="flex list-none snap-x gap-3 overflow-x-auto p-0 pb-1 sm:grid sm:grid-cols-2 sm:overflow-visible lg:grid-cols-3">
        {sorted.map((ticket) => {
          const kind = classifyTicketTier({
            name: ticket.name,
            isFree: ticket.is_free,
          });
          const badgeKey = TIER_BADGE_KEYS[kind];
          const left = tierSpotsRemaining(ticket.qty_cap, ticket.tickets_sold);
          const perks = splitTicketPerks(ticket.perks);
          const isTop = ticket.id === topId;
          return (
            <li
              key={ticket.id}
              className={`${cardClass} min-w-[15rem] shrink-0 snap-start sm:min-w-0 ${ticket.is_sold_out ? "opacity-60" : ""}`}
              style={isTop ? { borderColor: "var(--arch-accent)", borderWidth: 2 } : undefined}
              data-tier-kind={kind}
            >
              {badgeKey ? (
                <p className="text-xs font-semibold uppercase tracking-[0.14em] text-text-3">
                  {t(badgeKey)}
                </p>
              ) : null}
              <p className="font-display text-h3 text-display-ink">{ticket.name}</p>
              <p className="mt-1 text-lg font-semibold text-price">
                {ticket.is_free ? t("detail.free") : formatK(ticket.price_ngwee)}
              </p>
              {ticket.early_bird_price_ngwee !== null && !ticket.is_free ? (
                <p className="text-xs text-success">
                  {t("archetype.tier.earlyBird", {
                    price: formatK(ticket.early_bird_price_ngwee),
                  })}
                </p>
              ) : null}
              {perks.length > 0 ? (
                <ul className="mt-2 list-disc pl-5 text-sm text-text-2">
                  {perks.map((perk) => (
                    <li key={perk}>{perk}</li>
                  ))}
                </ul>
              ) : null}
              <p className="mt-2 text-xs font-semibold text-text-3">
                {ticket.is_sold_out
                  ? t("detail.soldOut")
                  : left !== null && left > 0
                    ? t("detail.ticketRemaining", { count: left })
                    : ""}
              </p>
            </li>
          );
        })}
      </ul>
      {donationNote ? <p className="text-sm text-text-2">{donationNote}</p> : null}
      <Link
        href="#tickets"
        className="inline-flex min-h-11 w-fit items-center text-sm font-semibold text-primary underline-offset-4 hover:underline focus-visible:outline-none focus-visible:shadow-focusRing lg:hidden"
      >
        {t("archetype.tier.choose")}
      </Link>
    </section>
  );
}
