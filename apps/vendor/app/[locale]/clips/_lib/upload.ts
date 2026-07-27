/**
 * M17-P06 — client-side file validation and the direct-to-Cloudinary upload.
 *
 * Two things this module is careful about, both of them about a vendor's own
 * money:
 *
 * 1. **Reject over-limit files before a byte leaves the phone.** The server cap
 *    is the real gate, but discovering the limit *after* uploading 80 MB on a
 *    mobile bundle is a cost the vendor already paid.
 * 2. **Retry without re-selecting or re-encoding.** A 3G upload will fail. The
 *    retry reuses the same `File` handle and the same signed params, so a failure
 *    costs the bytes already sent and nothing else — no second file picker, no
 *    second draft, and no phantom clip.
 *
 * `XMLHttpRequest` rather than `fetch`, deliberately: it is the only browser API
 * that reports **upload** progress, and a progress bar that does not move on a
 * slow connection is how a vendor concludes the app is broken and starts over.
 */

/** D-V3 caps, mirrored from the API so the client can refuse early. */
export const MAX_CLIP_BYTES = 83_886_080;
export const MAX_CLIP_DURATION_S = 60;

export type FileProblem = "not_video" | "too_large" | "too_long";

export function validateFile(file: { type?: string; size?: number }): FileProblem | null {
  if (!file.type || !file.type.startsWith("video/")) {
    return "not_video";
  }
  if ((file.size ?? 0) > MAX_CLIP_BYTES) {
    return "too_large";
  }
  return null;
}

export function validateDuration(seconds: number | null | undefined): FileProblem | null {
  if (typeof seconds !== "number" || !Number.isFinite(seconds)) {
    // Unknown duration is not a rejection: some browsers cannot read metadata
    // from a freshly captured file, and the server checks the real duration
    // from the transcode result anyway.
    return null;
  }
  return seconds > MAX_CLIP_DURATION_S ? "too_long" : null;
}

/** Read a video's duration in the browser without decoding the whole file. */
export function readDuration(file: Blob): Promise<number | null> {
  return new Promise((resolve) => {
    if (typeof document === "undefined" || typeof URL.createObjectURL !== "function") {
      resolve(null);
      return;
    }
    const element = document.createElement("video");
    const objectUrl = URL.createObjectURL(file);
    const done = (value: number | null) => {
      URL.revokeObjectURL(objectUrl);
      resolve(value);
    };
    element.preload = "metadata";
    element.onloadedmetadata = () =>
      done(Number.isFinite(element.duration) ? element.duration : null);
    element.onerror = () => done(null);
    element.src = objectUrl;
  });
}

export type SignedParams = {
  cloud_name: string;
  api_key: string;
  timestamp: number;
  signature: string;
  folder: string;
  eager: string;
  eager_async: string;
  duration: number;
  public_id?: string | null;
  notification_url?: string | null;
  eager_notification_url?: string | null;
};

export function cloudinaryUploadUrl(cloudName: string): string {
  return `https://api.cloudinary.com/v1_1/${encodeURIComponent(cloudName)}/video/upload`;
}

/**
 * Build the multipart body. **Every signed parameter must also be sent** — a
 * signed-but-omitted (or unsigned-but-sent) param is the documented cause of
 * Cloudinary's `#416 Invalid Signature`, which is the single most common way
 * this integration breaks.
 */
export function buildUploadForm(params: SignedParams, file: Blob, formData: FormData): FormData {
  formData.append("file", file);
  formData.append("api_key", params.api_key);
  formData.append("timestamp", String(params.timestamp));
  formData.append("signature", params.signature);
  formData.append("folder", params.folder);
  formData.append("eager", params.eager);
  formData.append("eager_async", params.eager_async);
  formData.append("duration", String(params.duration));
  if (params.public_id) {
    formData.append("public_id", params.public_id);
  }
  if (params.eager_notification_url) {
    formData.append("eager_notification_url", params.eager_notification_url);
  }
  if (params.notification_url) {
    formData.append("notification_url", params.notification_url);
  }
  return formData;
}

export type UploadHandle = {
  promise: Promise<void>;
  abort: () => void;
};

export function uploadToCloudinary(
  params: SignedParams,
  file: Blob,
  onProgress: (percent: number) => void,
): UploadHandle {
  const request = new XMLHttpRequest();
  const promise = new Promise<void>((resolve, reject) => {
    request.open("POST", cloudinaryUploadUrl(params.cloud_name));
    request.upload.onprogress = (event) => {
      if (event.lengthComputable && event.total > 0) {
        onProgress(Math.round((event.loaded / event.total) * 100));
      }
    };
    request.onload = () => {
      if (request.status >= 200 && request.status < 300) {
        onProgress(100);
        resolve();
        return;
      }
      reject(new Error(`upload_failed_${request.status}`));
    };
    request.onerror = () => reject(new Error("upload_network_error"));
    request.onabort = () => reject(new Error("upload_aborted"));
    request.send(buildUploadForm(params, file, new FormData()));
  });

  return { promise, abort: () => request.abort() };
}
