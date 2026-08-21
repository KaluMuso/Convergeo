export const EVENT_DATE_WINDOWS = ["tonight", "this_weekend", "all"] as const;
export const EVENT_CATEGORIES = [
  "workshops",
  "comedy-theatre",
  "pop-up-dinners",
  "cultural-arts",
  "lifestyle-community",
  "free-rsvp",
] as const;

export type EventDateWindow = "tonight" | "this_weekend" | "all";
export type EventCategory = (typeof EVENT_CATEGORIES)[number];
