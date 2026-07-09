"use client";

import { createApiClient } from "@vergeo/config";
import { useTranslations } from "next-intl";
import { useCallback, useMemo, useState } from "react";

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

type LogoUploadProps = {
  logoUrl: string | null;
  disabled: boolean;
  getToken: () => string | null | Promise<string | null>;
  onUploaded: (secureUrl: string) => void;
};

export function LogoUpload({ logoUrl, disabled, getToken, onUploaded }: LogoUploadProps) {
  const t = useTranslations("vendor");
  const [uploading, setUploading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const apiClient = useMemo(
    () =>
      createApiClient({
        baseUrl: process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000",
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
        setError(t("profile.logo.uploadFailed"));
      } finally {
        setUploading(false);
      }
    },
    [apiClient, onUploaded, t],
  );

  return (
    <div className="space-y-3">
      <div className="flex items-center gap-4">
        <div className="flex h-20 w-20 items-center justify-center overflow-hidden rounded-xl border border-neutral-200 bg-white">
          {logoUrl ? (
            <img src={logoUrl} alt={t("profile.logo.alt")} className="h-full w-full object-cover" />
          ) : (
            <span className="text-xs text-neutral-400">{t("profile.logo.empty")}</span>
          )}
        </div>
        <div className="flex flex-col gap-2">
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
              loadingLabel={t("profile.logo.uploading")}
            >
              {t("profile.logo.upload")}
            </Button>
          </label>
          <p className="text-xs text-neutral-500">{t("profile.logo.help")}</p>
        </div>
      </div>
      {uploading ? <Spinner label={t("profile.logo.uploading")} /> : null}
      {error ? <p className="text-sm text-red-600">{error}</p> : null}
    </div>
  );
}
