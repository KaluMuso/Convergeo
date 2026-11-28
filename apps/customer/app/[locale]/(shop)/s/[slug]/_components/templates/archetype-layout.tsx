import { isBespoke, type Archetype } from "../../_lib/archetypes";

import { AccommodationLayout } from "./accommodation-layout";
import { AppointmentLayout } from "./appointment-layout";
import { MembershipLayout } from "./membership-layout";
import { RentalLayout } from "./rental-layout";

import type { LayoutProps } from "./shared";

/**
 * Picks the main-column layout for an archetype. Returns null for archetypes without a
 * bespoke layout, so the caller renders the generic page (today's package comparison).
 */
export function ArchetypeLayout({ archetype, ...props }: LayoutProps & { archetype: Archetype }) {
  if (!isBespoke(archetype)) return null;
  switch (archetype) {
    case "accommodation":
      return <AccommodationLayout {...props} />;
    case "appointment":
      return <AppointmentLayout {...props} />;
    case "membership":
      return <MembershipLayout {...props} />;
    case "rental":
      return <RentalLayout {...props} />;
    default:
      return null;
  }
}
