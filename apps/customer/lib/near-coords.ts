/**
 * Coarse customer location remembered for this browser tab only (sessionStorage),
 * set when the customer turns on "Near me" in search. Rounded to ~1 km; never
 * sent anywhere — used client-side to show distances (e.g. "Other branches").
 */
const KEY = "cv_near";

export type NearCoords = { lat: number; lng: number };

function valid(lat: number, lng: number): boolean {
  return (
    Number.isFinite(lat) &&
    Number.isFinite(lng) &&
    Math.abs(lat) <= 90 &&
    Math.abs(lng) <= 180
  );
}

export function rememberNearCoords(lat: number, lng: number): void {
  if (!valid(lat, lng)) return;
  try {
    window.sessionStorage.setItem(KEY, `${lat},${lng}`);
  } catch {
    // Storage blocked (private mode): distances simply stay hidden.
  }
}

export function forgetNearCoords(): void {
  try {
    window.sessionStorage.removeItem(KEY);
  } catch {
    // ignore
  }
}

/** URL `?lat=&lng=` wins; else the remembered "Near me" coordinates; else null. */
export function readNearCoords(search: string): NearCoords | null {
  const params = new URLSearchParams(search);
  const fromUrl = [params.get("lat"), params.get("lng")];
  let raw: string | null = null;
  if (fromUrl[0] !== null && fromUrl[1] !== null) {
    raw = `${fromUrl[0]},${fromUrl[1]}`;
  } else {
    try {
      raw = window.sessionStorage.getItem(KEY);
    } catch {
      raw = null;
    }
  }
  if (!raw) return null;
  const [lat, lng] = raw.split(",").map(Number);
  return lat !== undefined && lng !== undefined && valid(lat, lng)
    ? { lat, lng }
    : null;
}

/** Great-circle distance in metres (same formula as the API's haversine_m). */
export function distanceMetres(a: NearCoords, b: NearCoords): number {
  const rad = Math.PI / 180;
  const dLat = (b.lat - a.lat) * rad;
  const dLng = (b.lng - a.lng) * rad;
  const h =
    Math.sin(dLat / 2) ** 2 +
    Math.cos(a.lat * rad) * Math.cos(b.lat * rad) * Math.sin(dLng / 2) ** 2;
  return 2 * 6_371_000 * Math.asin(Math.min(1, Math.sqrt(h)));
}
