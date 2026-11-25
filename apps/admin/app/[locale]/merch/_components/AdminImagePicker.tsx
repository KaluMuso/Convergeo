"use client";

import { getBrowserAccessToken } from "@vergeo/auth";
import { createApiClient } from "@vergeo/config";
import { CloudinaryImage } from "@vergeo/ui/src/media/cloudinary-image";
import { useTranslations } from "next-intl";
import { useCallback, useMemo, useRef, useState } from "react";

import { downscaleImageFile, uploadSignedImage } from "../../../../lib/admin-image-upload";
import { getApiBaseUrl } from "../../../../lib/api-base-url";
import { adminPrimaryButtonSmClass } from "../../_components/admin-primary-button";

type SignUploadResponse = {
  cloud_name: string;
  api_key: string;
  timestamp: number;
  signature: string;
  folder: string;
  allowed_formats: string;
  max_file_size: number;
};

type AdminImagePickerProps = {
  label: string;
  value: string;
  onChange: (publicId: string) => void;
  maxImages?: number;
};

export function AdminImagePicker({ label, value, onChange, maxImages = 1 }: AdminImagePickerProps) {
  const t = useTranslations("admin.merch.imagePicker");
  const inputRef = useRef<HTMLInputElement>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const apiClient = useMemo(
    () =>
      createApiClient({
        baseUrl: getApiBaseUrl(),
        getToken: getBrowserAccessToken,
      }),
    [],
  );

  const upload = useCallback(
    async (fileList: FileList | null) => {
      if (!fileList?.length) return;
      const files = Array.from(fileList);
      if (files.length !== 1) {
        return;
      }
      setBusy(true);
      setError(null);
      try {
        const file = files[0]!;
        const resized = await downscaleImageFile(file);
        const signed = await apiClient.request<SignUploadResponse>("/media/sign", {
          method: "POST",
          body: JSON.stringify({
            resource_kind: "listing",
            file_size_bytes: resized.size,
          }),
        });
        const uploaded = await uploadSignedImage(resized, signed);
        onChange(uploaded.public_id);
      } catch {
        setError(t("failure"));
      } finally {
        setBusy(false);
        if (inputRef.current) {
          inputRef.current.value = "";
        }
      }
    },
    [apiClient, maxImages, onChange, t, value],
  );

  return (
    <div className="space-y-2">
      <span className="text-xs text-muted">{label}</span>
      {value ? (
        <div className="relative h-28 w-full max-w-xs overflow-hidden rounded-md border border-border bg-bg">
          <CloudinaryImage publicId={value} alt="" width={320} ratio="16/9" className="size-full" />
        </div>
      ) : null}
      <div className="flex flex-wrap items-center gap-2">
        <button
          type="button"
          disabled={busy}
          className={adminPrimaryButtonSmClass}
          onClick={() => inputRef.current?.click()}
        >
          {busy ? t("uploading") : value ? t("replace") : t("upload")}
        </button>
        {value ? (
          <button
            type="button"
            className="text-xs text-danger underline"
            onClick={() => onChange("")}
          >
            {t("remove")}
          </button>
        ) : null}
      </div>
      <input
        ref={inputRef}
        type="file"
        accept="image/*"
        className="sr-only"
        onChange={(event) => void upload(event.target.files)}
      />
      {error ? (
        <p className="text-xs text-danger" role="alert">
          {error}
        </p>
      ) : null}
    </div>
  );
}
