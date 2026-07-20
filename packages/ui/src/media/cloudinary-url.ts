const CLOUDINARY_HOST = "res.cloudinary.com";
const DEFAULT_WIDTHS = [360, 720, 1080] as const;

export type CldUrlOptions = {
  width: number;
  quality?: number | "auto";
  cloudName?: string;
};

export type CldSrcSetOptions = {
  widths?: readonly number[];
  quality?: number | "auto";
  cloudName?: string;
};

function resolveCloudName(cloudName?: string): string | null {
  const resolved = cloudName ?? process.env.NEXT_PUBLIC_CLOUDINARY_CLOUD_NAME;
  if (!resolved || !resolved.trim()) {
    return null;
  }
  return resolved.trim();
}

/** Strip protocol-smuggling attempts while preserving intentional path slashes. */
export function sanitizePublicId(publicId: string): string {
  const trimmed = publicId.trim();
  if (!trimmed) {
    throw new Error("publicId must not be empty");
  }

  let sanitized = trimmed.replace(/^https?:\/\//i, "");
  sanitized = sanitized.replace(/:\/\//g, "");

  return sanitized;
}

export function cldUrl(publicId: string, options: CldUrlOptions): string {
  const safeId = sanitizePublicId(publicId);
  const cloud = resolveCloudName(options.cloudName);
  if (!cloud) {
    // Soft-fail: discovery grids must not throw when env is missing (ops gap).
    return "";
  }
  const quality = options.quality ?? "auto";
  const qualityToken = quality === "auto" ? "q_auto" : `q_${quality}`;

  return `https://${CLOUDINARY_HOST}/${cloud}/image/upload/f_auto,${qualityToken},w_${options.width}/${safeId}`;
}

export function cldLqipUrl(publicId: string, options?: { cloudName?: string }): string {
  const safeId = sanitizePublicId(publicId);
  const cloud = resolveCloudName(options?.cloudName);
  if (!cloud) {
    return "";
  }
  return `https://${CLOUDINARY_HOST}/${cloud}/image/upload/w_24,e_blur:1000,q_30/${safeId}`;
}

export function cldSrcSet(publicId: string, options?: CldSrcSetOptions): string {
  const widths = options?.widths ?? DEFAULT_WIDTHS;
  return widths
    .map(
      (width) =>
        `${cldUrl(publicId, { width, quality: options?.quality, cloudName: options?.cloudName })} ${width}w`,
    )
    .join(", ");
}
