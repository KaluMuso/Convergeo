/** Disposable performance-CI fixture contract; ordinary builds stay on Cloudinary. */
export const CI_PERF_IMAGE_ID = "ci-perf/smartphone-x1";
export const CI_PERF_MEDIA_PATH = "/api/ci-perf-media";
export const CI_PERF_PROXY_PATH = "/api/ci-perf";

export type CiPerfPublicEnv = {
  NEXT_PUBLIC_CI_PERF_HARNESS?: string;
  NEXT_PUBLIC_DEPLOYMENT_PLANE?: string;
  NEXT_PUBLIC_API_BASE_URL?: string;
  NEXT_PUBLIC_SITE_URL?: string;
};

export function ciPerfPublicEnv(): CiPerfPublicEnv {
  // Direct reads are required for Next's browser build-time substitutions.
  return {
    NEXT_PUBLIC_CI_PERF_HARNESS: process.env.NEXT_PUBLIC_CI_PERF_HARNESS,
    NEXT_PUBLIC_DEPLOYMENT_PLANE: process.env.NEXT_PUBLIC_DEPLOYMENT_PLANE,
    NEXT_PUBLIC_API_BASE_URL: process.env.NEXT_PUBLIC_API_BASE_URL,
    NEXT_PUBLIC_SITE_URL: process.env.NEXT_PUBLIC_SITE_URL,
  };
}

export function isCiPerfUpstream(origin: string | undefined): origin is string {
  const match = /^http:\/\/(\d{1,3})\.(\d{1,3})\.(\d{1,3})\.(\d{1,3}):8000$/.exec(origin ?? "");
  if (!match) return false;
  const parts = match.slice(1).map(Number);
  if (parts.some((part, index) => part > 255 || String(part) !== match[index + 1])) return false;
  return (
    parts[0] === 10 ||
    (parts[0] === 172 && Number(match[2]) >= 16 && Number(match[2]) <= 31) ||
    (parts[0] === 192 && parts[1] === 168)
  );
}

export function ciPerfPublicEnabled(env: CiPerfPublicEnv = ciPerfPublicEnv()): boolean {
  return (
    env.NEXT_PUBLIC_CI_PERF_HARNESS === "1" &&
    env.NEXT_PUBLIC_DEPLOYMENT_PLANE === "preview" &&
    env.NEXT_PUBLIC_SITE_URL === "http://localhost:3000" &&
    isCiPerfUpstream(env.NEXT_PUBLIC_API_BASE_URL)
  );
}

export function ciPerfMediaUrl(publicId: string, width: number): string | null {
  if (!ciPerfPublicEnabled() || publicId !== CI_PERF_IMAGE_ID) return null;
  // The existing home hero requests 1440px; use the largest genuine owned
  // variant while retaining the normal responsive srcset and intrinsic layout.
  if (width === 1440) return `${CI_PERF_MEDIA_PATH}?width=1200`;
  if (![24, 360, 720, 1080, 1200].includes(width)) throw new Error("Unsupported CI fixture width");
  return `${CI_PERF_MEDIA_PATH}?width=${width}`;
}
