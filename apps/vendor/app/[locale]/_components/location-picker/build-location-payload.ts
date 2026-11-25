import type { ProfilePatchPayload } from "../../profile/_lib/profile-client";
import type { VendorProfile } from "../../profile/_lib/profile-client";

export type LocationFields = {
  lat: string;
  lng: string;
  landmark: string;
};

/** Build profile `location` for PATCH — preserves saved GPS when hours change without retyping coords. */
export function buildLocationPayload(
  profile: VendorProfile | null,
  fields: LocationFields,
): ProfilePatchPayload["location"] | undefined {
  const parsedLat = Number.parseFloat(fields.lat);
  const parsedLng = Number.parseFloat(fields.lng);
  const landmarkTrim = fields.landmark.trim();

  const lat = Number.isFinite(parsedLat) ? parsedLat : (profile?.lat ?? null);
  const lng = Number.isFinite(parsedLng) ? parsedLng : (profile?.lng ?? null);

  if (lat == null || lng == null || !landmarkTrim) {
    return undefined;
  }

  return { lat, lng, landmark: landmarkTrim };
}
