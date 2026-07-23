import { notFound } from "next/navigation";

/**
 * Catch unknown locale-prefixed paths so `app/[locale]/not-found.tsx` renders
 * inside the locale layout (LinkButton CTAs, i18n) instead of the root fallback.
 */
export default function LocaleCatchAllPage() {
  notFound();
}
