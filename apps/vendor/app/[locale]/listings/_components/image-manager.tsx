"use client";

import { createApiClient } from "@vergeo/config";
import { useTranslations } from "next-intl";
import { useCallback, useMemo, useState } from "react";

import { CloudinaryImage } from "../../../../../../packages/ui/src/media/cloudinary-image";
import { UploadDropzone } from "../../../../../../packages/ui/src/media/upload-dropzone";
import { getApiBaseUrl } from "../../../../lib/api-base-url";

export const MAX_LISTING_IMAGES = 8;
export const DOWNSCALE_MAX_EDGE = 1600;
export const DOWNSCALE_QUALITY = 0.85;
const MAX_UPLOAD_RETRIES = 3;

export type ListingImageRecord = {
  id: string;
  cloudinary_public_id: string;
  position: number;
};

type SignUploadResponse = {
  cloud_name: string;
  api_key: string;
  timestamp: number;
  signature: string;
  folder: string;
  allowed_formats: string;
};

type CloudinaryUploadResponse = {
  public_id: string;
  secure_url?: string;
};

export type ImageManagerProps = {
  listingId: string;
  images: ListingImageRecord[];
  getToken: () => string | null | Promise<string | null>;
  onImagesChange?: (images: ListingImageRecord[]) => void;
};

type PendingUpload = {
  key: string;
  file: File;
  progress: number;
  error: string | null;
};

export function wouldExceedImageCap(currentCount: number, incomingCount: number): boolean {
  return currentCount + incomingCount > MAX_LISTING_IMAGES;
}

export async function downscaleImageFile(
  file: File,
  options: { maxEdge?: number; quality?: number; mimeType?: string } = {},
): Promise<File> {
  const maxEdge = options.maxEdge ?? DOWNSCALE_MAX_EDGE;
  const quality = options.quality ?? DOWNSCALE_QUALITY;
  const mimeType = options.mimeType ?? "image/jpeg";

  if (!file.type.startsWith("image/")) {
    return file;
  }

  const bitmap = await createImageBitmap(file);
  const longestEdge = Math.max(bitmap.width, bitmap.height);
  if (longestEdge <= maxEdge && file.size <= 2_000_000) {
    bitmap.close();
    return file;
  }

  const scale = Math.min(1, maxEdge / longestEdge);
  const width = Math.max(1, Math.round(bitmap.width * scale));
  const height = Math.max(1, Math.round(bitmap.height * scale));

  const canvas = document.createElement("canvas");
  canvas.width = width;
  canvas.height = height;
  const context = canvas.getContext("2d");
  if (!context) {
    bitmap.close();
    return file;
  }

  context.drawImage(bitmap, 0, 0, width, height);
  bitmap.close();

  const blob = await new Promise<Blob | null>((resolve) => {
    canvas.toBlob(resolve, mimeType, quality);
  });
  if (!blob) {
    return file;
  }

  const baseName = file.name.replace(/\.[^.]+$/, "") || "listing-image";
  return new File([blob], `${baseName}.jpg`, { type: mimeType, lastModified: Date.now() });
}

export async function uploadToCloudinaryWithProgress(
  file: Blob,
  signed: SignUploadResponse,
  onProgress: (progress: number) => void,
): Promise<CloudinaryUploadResponse> {
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    xhr.open("POST", `https://api.cloudinary.com/v1_1/${signed.cloud_name}/image/upload`);

    xhr.upload.onprogress = (event) => {
      if (!event.lengthComputable) {
        return;
      }
      onProgress(Math.round((event.loaded / event.total) * 100));
    };

    xhr.onload = () => {
      if (xhr.status < 200 || xhr.status >= 300) {
        reject(new Error("Cloudinary upload failed"));
        return;
      }
      try {
        const payload = JSON.parse(xhr.responseText) as CloudinaryUploadResponse;
        if (!payload.public_id) {
          reject(new Error("Cloudinary response missing public_id"));
          return;
        }
        resolve(payload);
      } catch {
        reject(new Error("Invalid Cloudinary response"));
      }
    };

    xhr.onerror = () => {
      reject(new Error("Network error during Cloudinary upload"));
    };

    const formData = new FormData();
    formData.append("file", file);
    formData.append("api_key", signed.api_key);
    formData.append("timestamp", String(signed.timestamp));
    formData.append("signature", signed.signature);
    formData.append("folder", signed.folder);
    formData.append("allowed_formats", signed.allowed_formats);
    xhr.send(formData);
  });
}

export async function uploadWithRetry(
  file: Blob,
  signed: SignUploadResponse,
  onProgress: (progress: number) => void,
  maxAttempts: number = MAX_UPLOAD_RETRIES,
): Promise<CloudinaryUploadResponse> {
  let lastError: Error | null = null;
  for (let attempt = 1; attempt <= maxAttempts; attempt += 1) {
    try {
      return await uploadToCloudinaryWithProgress(file, signed, onProgress);
    } catch (error) {
      lastError = error instanceof Error ? error : new Error("Upload failed");
      if (attempt < maxAttempts) {
        onProgress(0);
      }
    }
  }
  throw lastError ?? new Error("Upload failed");
}

function sortByPosition(images: ListingImageRecord[]): ListingImageRecord[] {
  return [...images].sort((left, right) => left.position - right.position);
}

export function ImageManager({ listingId, images, getToken, onImagesChange }: ImageManagerProps) {
  const t = useTranslations("vendor");
  const [localImages, setLocalImages] = useState<ListingImageRecord[]>(() =>
    sortByPosition(images),
  );
  const [pendingFiles, setPendingFiles] = useState<File[]>([]);
  const [pendingUploads, setPendingUploads] = useState<PendingUpload[]>([]);
  const [busy, setBusy] = useState(false);
  const [rejectNotice, setRejectNotice] = useState<string | null>(null);

  const apiClient = useMemo(
    () =>
      createApiClient({
        baseUrl: getApiBaseUrl(),
        getToken,
      }),
    [getToken],
  );

  const totalCount = localImages.length + pendingFiles.length;
  const fileProgress = pendingUploads.map((upload) => upload.progress);

  const syncImages = useCallback(
    (next: ListingImageRecord[]) => {
      const sorted = sortByPosition(next);
      setLocalImages(sorted);
      onImagesChange?.(sorted);
    },
    [onImagesChange],
  );

  const handleReject = useCallback(
    (attemptedCount: number) => {
      if (attemptedCount > MAX_LISTING_IMAGES) {
        setRejectNotice(t("listings.images.limit_reached"));
      }
    },
    [t],
  );

  const handleFilesChange = useCallback(
    (files: File[]) => {
      setRejectNotice(null);
      if (wouldExceedImageCap(localImages.length, files.length)) {
        setRejectNotice(t("listings.images.limit_reached"));
        return;
      }
      setPendingFiles(files);
    },
    [localImages.length, t],
  );

  const uploadPendingFiles = useCallback(async () => {
    if (pendingFiles.length === 0 || busy) {
      return;
    }
    if (wouldExceedImageCap(localImages.length, pendingFiles.length)) {
      setRejectNotice(t("listings.images.limit_reached"));
      return;
    }

    setBusy(true);
    setRejectNotice(null);
    const uploads: PendingUpload[] = pendingFiles.map((file, index) => ({
      key: `${file.name}-${file.lastModified}-${index}`,
      file,
      progress: 0,
      error: null,
    }));
    setPendingUploads(uploads);

    const attached: ListingImageRecord[] = [];
    try {
      for (let index = 0; index < pendingFiles.length; index += 1) {
        const sourceFile = pendingFiles[index];
        if (!sourceFile) {
          continue;
        }

        const updateProgress = (progress: number) => {
          setPendingUploads((current) =>
            current.map((item, itemIndex) => (itemIndex === index ? { ...item, progress } : item)),
          );
        };

        try {
          const downscaled = await downscaleImageFile(sourceFile);
          const signed = await apiClient.request<SignUploadResponse>("/media/sign", {
            method: "POST",
            body: JSON.stringify({
              resource_kind: "listing",
              file_size_bytes: downscaled.size,
            }),
          });

          const uploaded = await uploadWithRetry(downscaled, signed, updateProgress);
          const metadata = await apiClient.request<ListingImageRecord>(
            `/vendor/listings/${listingId}/images`,
            {
              method: "POST",
              body: JSON.stringify({ cloudinary_public_id: uploaded.public_id }),
            },
          );
          attached.push(metadata);
        } catch {
          setPendingUploads((current) =>
            current.map((item, itemIndex) =>
              itemIndex === index
                ? { ...item, error: t("listings.images.upload_failed"), progress: 0 }
                : item,
            ),
          );
          return;
        }
      }

      syncImages([...localImages, ...attached]);
      setPendingFiles([]);
      setPendingUploads([]);
    } finally {
      setBusy(false);
    }
  }, [apiClient, busy, listingId, localImages, pendingFiles, syncImages, t]);

  const moveImage = useCallback(
    async (fromIndex: number, direction: -1 | 1) => {
      const sorted = sortByPosition(localImages);
      const targetIndex = fromIndex + direction;
      if (targetIndex < 0 || targetIndex >= sorted.length) {
        return;
      }
      const next = [...sorted];
      const current = next[fromIndex];
      const swap = next[targetIndex];
      if (!current || !swap) {
        return;
      }
      next[fromIndex] = swap;
      next[targetIndex] = current;
      const reordered = await apiClient.request<ListingImageRecord[]>(
        `/vendor/listings/${listingId}/images/reorder`,
        {
          method: "PATCH",
          body: JSON.stringify({ image_ids: next.map((image) => image.id) }),
        },
      );
      syncImages(reordered);
    },
    [apiClient, listingId, localImages, syncImages],
  );

  const setCover = useCallback(
    async (imageId: string) => {
      const sorted = sortByPosition(localImages);
      const index = sorted.findIndex((image) => image.id === imageId);
      if (index <= 0) {
        return;
      }
      const next = [sorted[index], ...sorted.filter((_, itemIndex) => itemIndex !== index)];
      const filtered = next.filter((image): image is ListingImageRecord => Boolean(image));
      const reordered = await apiClient.request<ListingImageRecord[]>(
        `/vendor/listings/${listingId}/images/reorder`,
        {
          method: "PATCH",
          body: JSON.stringify({ image_ids: filtered.map((image) => image.id) }),
        },
      );
      syncImages(reordered);
    },
    [apiClient, listingId, localImages, syncImages],
  );

  const detachImage = useCallback(
    async (imageId: string) => {
      await apiClient.request<void>(`/vendor/listings/${listingId}/images/${imageId}`, {
        method: "DELETE",
      });
      syncImages(localImages.filter((image) => image.id !== imageId));
    },
    [apiClient, listingId, localImages, syncImages],
  );

  const retryFailedUpload = useCallback(() => {
    const failed = pendingUploads.filter((upload) => upload.error !== null);
    if (failed.length === 0) {
      return;
    }
    setPendingFiles(failed.map((upload) => upload.file));
    setPendingUploads([]);
  }, [pendingUploads]);

  return (
    <section data-testid="listing-image-manager" style={{ display: "grid", gap: "var(--sp-4)" }}>
      <header style={{ display: "grid", gap: "var(--sp-2)" }}>
        <h2>{t("listings.images.heading")}</h2>
        <p>{t("listings.images.intro", { count: totalCount, max: MAX_LISTING_IMAGES })}</p>
      </header>

      {localImages.length > 0 ? (
        <ul
          data-testid="listing-image-list"
          style={{
            listStyle: "none",
            margin: 0,
            padding: 0,
            display: "grid",
            gap: "var(--sp-3)",
          }}
        >
          {sortByPosition(localImages).map((image, index) => (
            <li
              key={image.id}
              data-testid={`listing-image-${index}`}
              style={{
                display: "grid",
                gridTemplateColumns: "auto 1fr auto",
                gap: "var(--sp-3)",
                alignItems: "center",
                border: "1px solid var(--border)",
                borderRadius: "var(--r)",
                padding: "var(--sp-3)",
              }}
            >
              <CloudinaryImage
                publicId={image.cloudinary_public_id}
                alt={t("listings.images.alt", { position: image.position })}
                width={72}
                ratio={1}
              />
              <div style={{ display: "grid", gap: "var(--sp-2)" }}>
                <span>
                  {image.position === 1
                    ? t("listings.images.cover_badge")
                    : t("listings.images.position_label", { position: image.position })}
                </span>
                <span style={{ fontFamily: "var(--font-mono)", fontSize: "0.875rem" }}>
                  {image.cloudinary_public_id}
                </span>
              </div>
              <div style={{ display: "flex", flexDirection: "column", gap: "var(--sp-1)" }}>
                <button
                  type="button"
                  aria-label={t("listings.images.move_up")}
                  disabled={index === 0 || busy}
                  onClick={() => moveImage(index, -1)}
                  style={{ minHeight: "44px", minWidth: "44px" }}
                >
                  {t("listings.images.move_up")}
                </button>
                <button
                  type="button"
                  aria-label={t("listings.images.move_down")}
                  disabled={index === localImages.length - 1 || busy}
                  onClick={() => moveImage(index, 1)}
                  style={{ minHeight: "44px", minWidth: "44px" }}
                >
                  {t("listings.images.move_down")}
                </button>
                {image.position !== 1 ? (
                  <button
                    type="button"
                    onClick={() => setCover(image.id)}
                    disabled={busy}
                    style={{ minHeight: "44px", minWidth: "44px" }}
                  >
                    {t("listings.images.set_cover")}
                  </button>
                ) : null}
                <button
                  type="button"
                  aria-label={t("listings.images.remove")}
                  disabled={busy}
                  onClick={() => detachImage(image.id)}
                  style={{ minHeight: "44px", minWidth: "44px" }}
                >
                  {t("listings.images.remove")}
                </button>
              </div>
            </li>
          ))}
        </ul>
      ) : null}

      {totalCount < MAX_LISTING_IMAGES ? (
        <UploadDropzone
          files={pendingFiles}
          onFilesChange={handleFilesChange}
          onReject={handleReject}
          fileProgress={fileProgress}
          dropLabel={t("listings.images.drop_label")}
          browseLabel={t("listings.images.browse_label")}
          moveUpLabel={t("listings.images.move_up")}
          moveDownLabel={t("listings.images.move_down")}
          removeLabel={t("listings.images.remove")}
          compressHint={t("listings.images.compress_hint")}
        />
      ) : null}

      {rejectNotice ? (
        <p role="alert" data-testid="image-limit-notice">
          {rejectNotice}
        </p>
      ) : null}

      {pendingFiles.length > 0 ? (
        <button
          type="button"
          data-testid="upload-images-button"
          disabled={busy}
          onClick={() => void uploadPendingFiles()}
          style={{ minHeight: "44px" }}
        >
          {busy ? t("listings.images.uploading") : t("listings.images.upload")}
        </button>
      ) : null}

      {pendingUploads.some((upload) => upload.error) ? (
        <button
          type="button"
          data-testid="retry-upload-button"
          onClick={retryFailedUpload}
          style={{ minHeight: "44px" }}
        >
          {t("listings.images.retry")}
        </button>
      ) : null}
    </section>
  );
}
