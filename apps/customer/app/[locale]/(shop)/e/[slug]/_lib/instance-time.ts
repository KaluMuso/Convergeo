export const LEGACY_EVENT_DURATION_MS = 2 * 60 * 60 * 1000;

export type EventInstanceTime = {
  starts_at: string;
  ends_at?: string | null;
};

export function effectiveInstanceEndMs(instance: EventInstanceTime): number {
  const startsAtMs = new Date(instance.starts_at).getTime();
  const endsAtMs = instance.ends_at ? new Date(instance.ends_at).getTime() : Number.NaN;

  if (Number.isFinite(endsAtMs) && (!Number.isFinite(startsAtMs) || endsAtMs > startsAtMs)) {
    return endsAtMs;
  }
  if (Number.isFinite(startsAtMs)) {
    return startsAtMs + LEGACY_EVENT_DURATION_MS;
  }
  return Number.NaN;
}

export function isPastEventInstance(
  instance: EventInstanceTime,
  now: number = Date.now(),
): boolean {
  const endsAtMs = effectiveInstanceEndMs(instance);
  return Number.isFinite(endsAtMs) && endsAtMs < now;
}
