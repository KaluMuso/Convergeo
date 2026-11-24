/** Client-side checks aligned with `POST /media/kyc-doc/sign` (10 MiB max). */

export const MAX_KYC_DOC_BYTES = 10_485_760;

export const ACCEPTED_KYC_IMAGE_TYPES = new Set(["image/jpeg", "image/png", "image/webp"]);

export type KycImageValidationProblem = "invalid_type" | "too_large";

export function validateKycImageFile(
  file: Pick<File, "type" | "size">,
): KycImageValidationProblem | null {
  if (!ACCEPTED_KYC_IMAGE_TYPES.has(file.type) || file.size < 1) {
    return "invalid_type";
  }
  if (file.size > MAX_KYC_DOC_BYTES) {
    return "too_large";
  }
  return null;
}

/** Rasterise and JPEG-encode like the in-camera capture path (0.85 quality). */
export async function prepareKycImageFile(file: File): Promise<File> {
  const problem = validateKycImageFile(file);
  if (problem) {
    throw new Error(problem);
  }

  const bitmap = await createImageBitmap(file);
  const width = bitmap.width || 640;
  const height = bitmap.height || 480;

  const canvas = document.createElement("canvas");
  canvas.width = width;
  canvas.height = height;
  const ctx = canvas.getContext("2d");
  if (!ctx) {
    bitmap.close();
    return file;
  }
  ctx.drawImage(bitmap, 0, 0, width, height);
  bitmap.close();

  const blob = await new Promise<Blob | null>((resolve) => {
    canvas.toBlob(resolve, "image/jpeg", 0.85);
  });
  if (!blob) {
    throw new Error("encode_failed");
  }
  if (blob.size > MAX_KYC_DOC_BYTES) {
    throw new Error("too_large");
  }

  return new File([blob], `upload-${Date.now()}.jpg`, {
    type: "image/jpeg",
    lastModified: Date.now(),
  });
}
