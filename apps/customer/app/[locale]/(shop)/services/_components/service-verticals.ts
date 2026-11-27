export const SERVICE_VERTICALS = [
  "lodging",
  "property",
  "beauty",
  "fitness",
  "cleaning",
  "home-services",
  "rentals",
  "family-fun",
  "auto",
  "tailoring",
  "food-catering",
  "printing-creative",
  "tech-services",
  "staffing",
] as const;

export type ServiceVerticalKey = (typeof SERVICE_VERTICALS)[number];

/** Vertical to archetype (mirrors `services/api/app/schemas/service_archetypes.py`). */
export const VERTICAL_ARCHETYPE: Record<ServiceVerticalKey, string> = {
  lodging: "accommodation",
  property: "accommodation",
  beauty: "appointment",
  tailoring: "appointment",
  auto: "appointment",
  fitness: "membership",
  cleaning: "on_site",
  "home-services": "on_site",
  rentals: "rental",
  "family-fun": "ticketed",
  "tech-services": "professional",
  "printing-creative": "professional",
  "food-catering": "professional",
  staffing: "professional",
};
