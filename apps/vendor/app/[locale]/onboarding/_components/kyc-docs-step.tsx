"use client";

import { useState } from "react";

import { isValidZmMobile, normalizeZmPhone } from "../_lib/kyc-client";
import { Button, FormField, Input, Spinner } from "../_lib/ui";

import { DocCapture } from "./doc-capture";
import { ImageQualityHints } from "./image-quality-hints";

import type { KycDocType } from "../_lib/types";
import type { ChangeEvent, FormEvent } from "react";

type KycDocsStepProps = {
  momoPhone: string;
  nrcPath: string | null;
  selfiePath: string | null;
  rejectedDocs?: KycDocType[] | null;
  onMomoPhoneChange: (value: string) => void;
  onNrcUploaded: (path: string) => void;
  onSelfieUploaded: (path: string) => void;
  onContinue: () => void;
  onUpload: (docType: KycDocType, file: File) => Promise<string>;
  labels: {
    heading: string;
    intro: string;
    nrcLabel: string;
    nrcHelp: string;
    selfieLabel: string;
    selfieHelp: string;
    momoLabel: string;
    momoPlaceholder: string;
    momoHelp: string;
    continue: string;
    uploading: string;
    capture: string;
    retake: string;
    usePhoto: string;
    uploadFailed: string;
    uploaded: string;
    nrcDone: string;
    selfieDone: string;
    required: string;
    invalidPhone: string;
    quality: {
      heading: string;
      light: string;
      steady: string;
      frame: string;
      face: string;
    };
  };
};

export function KycDocsStep({
  momoPhone,
  nrcPath,
  selfiePath,
  rejectedDocs = null,
  onMomoPhoneChange,
  onNrcUploaded,
  onSelfieUploaded,
  onContinue,
  onUpload,
  labels,
}: KycDocsStepProps) {
  const [uploading, setUploading] = useState<KycDocType | null>(null);
  const [uploadError, setUploadError] = useState<string | null>(null);

  const needsNrc = !rejectedDocs || rejectedDocs.includes("nrc");
  const needsSelfie = !rejectedDocs || rejectedDocs.includes("selfie");

  const phoneError = !momoPhone.trim()
    ? labels.required
    : !isValidZmMobile(normalizeZmPhone(momoPhone))
      ? labels.invalidPhone
      : undefined;

  const canContinue =
    (!needsNrc || Boolean(nrcPath)) &&
    (!needsSelfie || Boolean(selfiePath)) &&
    !phoneError &&
    !uploading;

  const handleUpload = async (docType: KycDocType, file: File) => {
    setUploadError(null);
    setUploading(docType);
    try {
      const path = await onUpload(docType, file);
      if (docType === "nrc") {
        onNrcUploaded(path);
      } else {
        onSelfieUploaded(path);
      }
    } catch {
      setUploadError(labels.uploadFailed);
    } finally {
      setUploading(null);
    }
  };

  const handleSubmit = (event: FormEvent) => {
    event.preventDefault();
    if (!canContinue) {
      return;
    }
    onContinue();
  };

  return (
    <form className="flex flex-col gap-4" onSubmit={handleSubmit}>
      <header className="space-y-1">
        <h1 className="font-display text-h3 text-display-ink">{labels.heading}</h1>
        <p className="text-sm text-text-2">{labels.intro}</p>
      </header>

      <ImageQualityHints {...labels.quality} />

      {needsNrc ? (
        <div className="relative">
          {uploading === "nrc" ? (
            <div className="absolute inset-0 z-10 flex items-center justify-center rounded bg-surface/80">
              <Spinner label={labels.uploading} />
            </div>
          ) : null}
          <DocCapture
            label={labels.nrcLabel}
            helpText={labels.nrcHelp}
            captureLabel={labels.capture}
            retakeLabel={labels.retake}
            usePhotoLabel={labels.usePhoto}
            facingMode="environment"
            disabled={uploading !== null}
            onCapture={(file) => void handleUpload("nrc", file)}
          />
          {nrcPath ? (
            <p className="mt-1 text-xs text-success" aria-live="polite">
              {labels.nrcDone}
            </p>
          ) : null}
        </div>
      ) : null}

      {needsSelfie ? (
        <div className="relative">
          {uploading === "selfie" ? (
            <div className="absolute inset-0 z-10 flex items-center justify-center rounded bg-surface/80">
              <Spinner label={labels.uploading} />
            </div>
          ) : null}
          <DocCapture
            label={labels.selfieLabel}
            helpText={labels.selfieHelp}
            captureLabel={labels.capture}
            retakeLabel={labels.retake}
            usePhotoLabel={labels.usePhoto}
            facingMode="user"
            disabled={uploading !== null}
            onCapture={(file) => void handleUpload("selfie", file)}
          />
          {selfiePath ? (
            <p className="mt-1 text-xs text-success" aria-live="polite">
              {labels.selfieDone}
            </p>
          ) : null}
        </div>
      ) : null}

      <FormField label={labels.momoLabel} helpText={labels.momoHelp} errorMessage={phoneError}>
        <Input
          type="tel"
          inputMode="tel"
          autoComplete="tel"
          value={momoPhone}
          onChange={(event: ChangeEvent<HTMLInputElement>) => onMomoPhoneChange(event.target.value)}
          placeholder={labels.momoPlaceholder}
          error={Boolean(phoneError)}
        />
      </FormField>

      {uploadError ? <p className="text-sm text-danger">{uploadError}</p> : null}

      <Button
        type="submit"
        className="w-full"
        loading={uploading !== null}
        loadingLabel={labels.uploading}
        disabled={!canContinue}
      >
        {labels.continue}
      </Button>
    </form>
  );
}
