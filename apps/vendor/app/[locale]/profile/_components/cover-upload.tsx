"use client";

import { createApiClient } from "@vergeo/config";
import { useTranslations } from "next-intl";
import { useCallback, useMemo, useState } from "react";

import { getApiBaseUrl } from "../../../../lib/api-base-url";
import {
  downscaleImageFile,
  uploadToCloudinaryWithProgress,
} from "../../listings/_components/image-manager";
import { Button, Spinner } from "../../listings/new/_lib/ui";

type SignUploadResponse = {
  cloud_name: string;
  api_key: string;
  timestamp: number;
  signature: string;
  folder: string;
  allowed_formats: string;
};

type CoverUploadProps = {
  coverUrl: string | null;
  disabled: boolean;
  getToken: () => string | null | Promise<string | null>;
  onUploaded: (secureUrl: string) => void;
  onRemove: () => void;
};

export function CoverUpload({
  coverUrl,
  disabled,
  getToken,
  onUploaded,
  onRemove,
}: CoverUploadProps) {
  const t = useTranslations("vendor");
  const [uploading, setUploading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const apiClient = useMemo(
    () =>
      createApiClient({
        baseUrl: getApiBaseUrl(),
        getToken,
      }),
    [getToken],
  );

  const handleFile = useCallback(
    async (fileList: FileList | null) => {
      const file = fileList?.[0];
      if (!file) {
        return;
      }
      setUploading(true);
      setError(null);
      try {
        const prepared = await downscaleImageFile(file);
        const signed = await apiClient.request<SignUploadResponse>("/media/sign", {
          method: "POST",
          body: JSON.stringify({
            resource_kind: "listing",
            file_size_bytes: prepared.size,
          }),
        });
        const uploaded = await uploadToCloudinaryWithProgress(prepared, signed, () => undefined);
        const secureUrl = uploaded.secure_url;
        if (!secureUrl) {
          throw new Error("missing secure_url");
        }
        onUploaded(secureUrl);
      } catch {
        setError(t("profile.cover.uploadFailed"));
      } finally {
        setUploading(false);
      }
    },
    [apiClient, onUploaded, t],
  );

  return (
    <div className="space-y-3">
      <div className="flex h-28 w-full items-center justify-center overflow-hidden rounded-xl border border-neutral-200 bg-neutral-50 sm:h-36">
        {coverUrl ? (
          <img src={coverUrl} alt={t("profile.cover.alt")} className="h-full w-full object-cover" />
        ) : (
          <span className="text-xs text-neutral-400">{t("profile.cover.empty")}</span>
        )}
      </div>
      <div className="flex flex-wrap items-center gap-2">
        <label className="inline-flex cursor-pointer">
          <input
            type="file"
            accept="image/*"
            className="sr-only"
            disabled={disabled || uploading}
            onChange={(event) => void handleFile(event.target.files)}
          />
          <Button
            type="button"
            variant="secondary"
            disabled={disabled || uploading}
            loading={uploading}
            loadingLabel={t("profile.cover.uploading")}
          >
            {t("profile.cover.upload")}
          </Button>
        </label>
        {coverUrl ? (
          <Button
            type="button"
            variant="ghost"
            disabled={disabled || uploading}
            loadingLabel={t("profile.cover.remove")}
            onClick={onRemove}
          >
            {t("profile.cover.remove")}
          </Button>
        ) : null}
      </div>
      <p className="text-xs text-neutral-500">{t("profile.cover.help")}</p>
      {uploading ? <Spinner label={t("profile.cover.uploading")} /> : null}
      {error ? <p className="text-sm text-red-600">{error}</p> : null}
    </div>
  );
}
