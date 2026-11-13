/** Exact runner-local service admission; this never supplies a fallback origin. */
export function isCiPerfSupabaseOrigin(origin: string | undefined): boolean {
  return origin === "http://127.0.0.1:54321";
}
