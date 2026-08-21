// Plain module — deliberately NOT "use client".
//
// `events/page.tsx` is a Server Component that reads these constants by value
// (`[...EVENT_CATEGORIES]`). A `"use client"` file's non-component exports do
// not cross the server/client boundary as the real value in the production RSC
// build, which surfaced as `EVENT_CATEGORIES.includes is not a function` on
// /events. Keeping the data here lets both sides import it safely.
export const EVENT_DATE_WINDOWS = [
  "tonight",
  "this_weekend",
  "next_week",
  "next_month",
  "all",
] as const;
export const EVENT_CATEGORIES = [
  "workshops",
  "comedy-theatre",
  "pop-up-dinners",
  "cultural-arts",
  "lifestyle-community",
  "free-rsvp",
] as const;

export type EventDateWindow = (typeof EVENT_DATE_WINDOWS)[number];
// Open on purpose: the API returns operator-defined categories beyond the
// built-in list, and `parseCategory()` passes the raw query value through.
export type EventCategory = string;
