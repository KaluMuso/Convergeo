const CLOUDINARY_UPLOAD = /^(https:\/\/res\.cloudinary\.com\/[^/]+\/image\/upload\/)(.+)$/;

/**
 * Display-sized rendition of an uploaded Cloudinary asset.
 *
 * Logo and cover previews were rendering the stored `secure_url` (the full client-side
 * downscaled upload) inside an 80px / 112px box. This inserts `f_auto,q_auto,w_<n>` so the
 * browser fetches a modern format at roughly display size. Anything that is not a
 * standard Cloudinary upload URL (blob: previews, other hosts) is returned untouched.
 */
export function cloudinaryPreviewUrl(url: string, width: number): string {
  const match = CLOUDINARY_UPLOAD.exec(url);
  if (!match) {
    return url;
  }
  const [, prefix, rest] = match as unknown as [string, string, string];
  const safeWidth = Math.max(16, Math.min(2000, Math.round(width)));
  return `${prefix}f_auto,q_auto,c_limit,w_${safeWidth}/${rest}`;
}
