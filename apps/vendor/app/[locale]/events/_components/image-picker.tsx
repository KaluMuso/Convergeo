"use client";

import { createApiClient } from "@vergeo/config";
import { useTranslations } from "next-intl";
import { useCallback, useMemo, useState } from "react";

import { CloudinaryImage } from "../../../../../../packages/ui/src/media/cloudinary-image";
import { getApiBaseUrl } from "../../../../lib/api-base-url";
import {
  downscaleImageFile,
  uploadWithRetry,
  wouldExceedImageCap,
} from "../../listings/_components/image-manager";
import { Button } from "../_lib/ui";

export const MAX_EVENT_IMAGES = 8;

type SignUploadResponse = {
  cloud_name: string;
  api_key: string;
  timestamp: number;
  signature: string;
  folder: string;
  allowed_formats: string;
  max_file_size: number;
};

export type EventImagePickerProps = {
  images: string[];
  getToken: () => string | null | Promise<string | null>;
  onChange: (images: string[]) => void;
  disabled?: boolean;
};

export function EventImagePicker({
  images,
  getToken,
  onChange,
  disabled = false,
}: EventImagePickerProps) {
  const t = useTranslations("vendor");
  const te = useTranslations("events");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const apiClient = useMemo(
    () =>
      createApiClient({
        baseUrl: getApiBaseUrl(),
        getToken,
      }),
    [getToken],
  );

  const handleFiles = useCallback(
    async (fileList: FileList | null) => {
      if (disabled || !fileList?.length) {
        return;
      }
      const files = Array.from(fileList);
      if (wouldExceedImageCap(images.length, files.length)) {
        setError(t("events.images.limit_reached"));
        return;
      }

      setBusy(true);
      setError(null);
      const next = [...images];

      try {
        for (const file of files) {
          const resized = await downscaleImageFile(file);
          const signed = await apiClient.request<SignUploadResponse>("/media/sign", {
            method: "POST",
            body: JSON.stringify({
              resource_kind: "listing",
              file_size_bytes: resized.size,
            }),
          });
          const uploaded = await uploadWithRetry(resized, signed, () => undefined);
          next.push(uploaded.public_id);
        }
        onChange(next.slice(0, MAX_EVENT_IMAGES));
      } catch {
        setError(t("events.images.upload_failed"));
      } finally {
        setBusy(false);
      }
    },
    [apiClient, disabled, images, onChange, t],
  );

  const removeAt = useCallback(
    (index: number) => {
      onChange(images.filter((_, position) => position !== index));
    },
    [images, onChange],
  );

  return (
    <section className="space-y-3">
      <div>
        <h2 className="text-sm font-semibold text-text">{t("events.images.heading")}</h2>
        <p className="text-xs text-text-2">
          {t("events.images.intro", { count: images.length, max: MAX_EVENT_IMAGES })}
        </p>
      </div>

      {images.length > 0 ? (
        <ul className="grid grid-cols-2 gap-2">
          {images.map((publicId, index) => (
            <li
              key={`${publicId}-${index}`}
              className="relative overflow-hidden rounded-lg border border-border"
            >
              <CloudinaryImage
                publicId={publicId}
                alt={te("organiser.imageAlt", { position: index + 1 })}
                width={160}
                ratio="1/1"
                className="aspect-square h-full w-full object-cover"
              />
              <button
                type="button"
                className="absolute right-1 top-1 rounded bg-surface/90 px-2 py-1 text-xs"
                onClick={() => removeAt(index)}
                disabled={disabled || busy}
              >
                {t("events.images.remove")}
              </button>
            </li>
          ))}
        </ul>
      ) : null}

      {images.length < MAX_EVENT_IMAGES ? (
        <label className="inline-flex">
          <input
            type="file"
            accept="image/*"
            multiple
            className="sr-only"
            disabled={disabled || busy}
            onChange={(event) => void handleFiles(event.target.files)}
          />
          <Button
            type="button"
            variant="secondary"
            disabled={disabled || busy}
            loading={busy}
            loadingLabel={t("events.images.uploading")}
          >
            {t("events.images.upload")}
          </Button>
        </label>
      ) : null}

      {error ? <p className="text-xs text-danger">{error}</p> : null}
    </section>
  );
}
