"use client";

import { CloudinaryImage } from "@vergeo/ui/src/media/cloudinary-image";
import { useTranslations } from "next-intl";
import { useCallback, useRef, useState } from "react";

import { downscaleImageFile, uploadSignedImage } from "../../../../lib/admin-image-upload";
import { adminPrimaryButtonSmClass } from "../../_components/admin-primary-button";

import { configApi, type CategoryNode } from "./api";
import {
  charCount,
  draftFromPresentation,
  draftToPayload,
  MAX_BANNER_DESCRIPTION_CHARS,
  MAX_BANNER_TITLE_CHARS,
  PRESENTATION_LOCALES,
  validateDraft,
  type CategoryPresentation,
  type CategoryPresentationDraft,
  type DraftProblem,
  type PresentationLocale,
} from "./category-presentation-api";

type SignUploadResponse = {
  cloud_name: string;
  api_key: string;
  timestamp: number;
  signature: string;
  folder: string;
  allowed_formats: string;
  max_file_size: number;
};

type MediaKind = "icon" | "banner";

/** Icons are shown at most ~96px; banners at most ~1280px wide. */
const MAX_EDGE: Record<MediaKind, number> = { icon: 512, banner: 1600 };

type MediaPickerProps = {
  kind: MediaKind;
  label: string;
  hint: string;
  value: string;
  onChange: (publicId: string) => void;
};

function CategoryMediaPicker({ kind, label, hint, value, onChange }: MediaPickerProps) {
  const t = useTranslations("admin.config.categories.look");
  const inputRef = useRef<HTMLInputElement>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const upload = useCallback(
    async (fileList: FileList | null) => {
      const file = fileList?.[0];
      if (!file) return;
      setBusy(true);
      setError(null);
      try {
        const resized = await downscaleImageFile(file, MAX_EDGE[kind]);
        const signed = await configApi.request<SignUploadResponse>(
          "/admin/config/category-media/sign",
          {
            method: "POST",
            body: JSON.stringify({ kind, file_size_bytes: resized.size }),
          },
        );
        const uploaded = await uploadSignedImage(resized, signed);
        onChange(uploaded.public_id);
      } catch {
        setError(t("uploadFailed"));
      } finally {
        setBusy(false);
        if (inputRef.current) {
          inputRef.current.value = "";
        }
      }
    },
    [kind, onChange, t],
  );

  return (
    <div className="space-y-2">
      <div>
        <span className="text-sm font-medium text-text">{label}</span>
        <p className="text-xs text-muted">{hint}</p>
      </div>
      {value ? (
        <div
          className={
            kind === "icon"
              ? "relative size-20 overflow-hidden rounded-full border border-border bg-bg"
              : "relative aspect-[3/1] w-full max-w-md overflow-hidden rounded-md border border-border bg-bg"
          }
          data-testid={`category-${kind}-preview`}
        >
          <CloudinaryImage
            publicId={value}
            alt=""
            width={kind === "icon" ? 160 : 640}
            ratio={kind === "icon" ? "1/1" : "3/1"}
            className="size-full object-cover"
          />
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
            className="min-h-11 text-xs text-danger underline"
            onClick={() => onChange("")}
          >
            {t("removeImage")}
          </button>
        ) : null}
      </div>
      <input
        ref={inputRef}
        type="file"
        accept="image/jpeg,image/png,image/webp,image/avif"
        className="sr-only"
        aria-label={label}
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

type EditorProps = {
  category: CategoryNode;
  presentation: CategoryPresentation | undefined;
  onSaved: (presentation: CategoryPresentation | null) => void;
  onClose: () => void;
};

export function CategoryPresentationEditor({
  category,
  presentation,
  onSaved,
  onClose,
}: EditorProps) {
  const t = useTranslations("admin.config.categories.look");
  const [draft, setDraft] = useState<CategoryPresentationDraft>(() =>
    draftFromPresentation(presentation),
  );
  const [locale, setLocale] = useState<PresentationLocale>("en");
  const [saving, setSaving] = useState(false);
  const [saveError, setSaveError] = useState<string | null>(null);

  const problems = validateDraft(draft);
  const blocking = problems.filter((problem) => problem.kind !== "empty");
  const canSave = problems.length === 0 && !saving;

  const setCopy = (field: "banner_title_i18n" | "banner_description_i18n", value: string) => {
    setDraft((current) => ({ ...current, [field]: { ...current[field], [locale]: value } }));
  };

  const problemText = (problem: DraftProblem): string => {
    switch (problem.kind) {
      case "titleTooLong":
        return t("titleTooLong", {
          locale: t(`locales.${problem.locale}`),
          max: MAX_BANNER_TITLE_CHARS,
        });
      case "descriptionTooLong":
        return t("descriptionTooLong", {
          locale: t(`locales.${problem.locale}`),
          max: MAX_BANNER_DESCRIPTION_CHARS,
        });
      case "englishRequired":
        return t("englishRequired");
      case "descriptionNeedsTitle":
        return t("descriptionNeedsTitle");
      default:
        return t("empty");
    }
  };

  const save = async () => {
    setSaving(true);
    setSaveError(null);
    try {
      const saved = await configApi.request<CategoryPresentation>(
        `/admin/config/categories/${category.id}/presentation`,
        { method: "PUT", body: JSON.stringify(draftToPayload(draft)) },
      );
      onSaved(saved);
    } catch {
      setSaveError(t("saveFailed"));
    } finally {
      setSaving(false);
    }
  };

  const clearAll = async () => {
    if (!presentation) {
      onClose();
      return;
    }
    setSaving(true);
    setSaveError(null);
    try {
      await configApi.request(`/admin/config/categories/${category.id}/presentation`, {
        method: "DELETE",
      });
      onSaved(null);
    } catch {
      setSaveError(t("saveFailed"));
    } finally {
      setSaving(false);
    }
  };

  const title = draft.banner_title_i18n[locale] ?? "";
  const description = draft.banner_description_i18n[locale] ?? "";
  const titleCount = charCount(title);
  const descriptionCount = charCount(description);

  return (
    <section
      className="space-y-4 rounded-lg border border-border bg-surface p-4"
      aria-label={t("panelLabel", { category: category.name })}
      data-testid="category-presentation-editor"
    >
      <div>
        <h3 className="text-sm font-semibold text-text">
          {t("panelTitle", { category: category.name })}
        </h3>
        <p className="text-xs text-muted">{t("panelSubtitle")}</p>
      </div>

      <div className="grid gap-4 sm:grid-cols-2">
        <CategoryMediaPicker
          kind="icon"
          label={t("iconLabel")}
          hint={t("iconHint")}
          value={draft.icon_public_id}
          onChange={(value) => setDraft((current) => ({ ...current, icon_public_id: value }))}
        />
        <CategoryMediaPicker
          kind="banner"
          label={t("bannerLabel")}
          hint={t("bannerHint")}
          value={draft.banner_public_id}
          onChange={(value) => setDraft((current) => ({ ...current, banner_public_id: value }))}
        />
      </div>

      <div className="space-y-3">
        <div role="tablist" aria-label={t("languageTabs")} className="flex flex-wrap gap-1">
          {PRESENTATION_LOCALES.map((code) => (
            <button
              key={code}
              type="button"
              role="tab"
              aria-selected={code === locale}
              className={
                code === locale
                  ? "min-h-11 rounded-md bg-primary px-3 text-sm font-medium text-[var(--primary-btn-fg)]"
                  : "min-h-11 rounded-md border border-border px-3 text-sm"
              }
              onClick={() => setLocale(code)}
            >
              {t(`locales.${code}`)}
            </button>
          ))}
        </div>
        {locale !== "en" ? <p className="text-xs text-muted">{t("fallbackHint")}</p> : null}

        <label className="flex flex-col gap-1 text-xs text-muted">
          <span className="flex justify-between gap-2">
            <span>{t("titleLabel")}</span>
            <span
              className={titleCount > MAX_BANNER_TITLE_CHARS ? "text-danger" : undefined}
              data-testid="banner-title-count"
            >
              {t("counter", { count: titleCount, max: MAX_BANNER_TITLE_CHARS })}
            </span>
          </span>
          <input
            type="text"
            value={title}
            maxLength={MAX_BANNER_TITLE_CHARS + 20}
            onChange={(event) => setCopy("banner_title_i18n", event.target.value)}
            className="min-h-11 rounded-md border border-border bg-surface px-3 text-sm text-text"
          />
        </label>

        <label className="flex flex-col gap-1 text-xs text-muted">
          <span className="flex justify-between gap-2">
            <span>{t("descriptionLabel")}</span>
            <span
              className={
                descriptionCount > MAX_BANNER_DESCRIPTION_CHARS ? "text-danger" : undefined
              }
              data-testid="banner-description-count"
            >
              {t("counter", { count: descriptionCount, max: MAX_BANNER_DESCRIPTION_CHARS })}
            </span>
          </span>
          <textarea
            value={description}
            rows={3}
            maxLength={MAX_BANNER_DESCRIPTION_CHARS + 40}
            onChange={(event) => setCopy("banner_description_i18n", event.target.value)}
            className="rounded-md border border-border bg-surface px-3 py-2 text-sm text-text"
          />
        </label>
      </div>

      {blocking.length > 0 ? (
        <ul className="space-y-1 text-xs text-danger" role="alert">
          {blocking.map((problem) => (
            <li key={`${problem.kind}-${"locale" in problem ? problem.locale : ""}`}>
              {problemText(problem)}
            </li>
          ))}
        </ul>
      ) : null}
      {saveError ? (
        <p className="text-xs text-danger" role="alert">
          {saveError}
        </p>
      ) : null}

      <div className="flex flex-wrap items-center gap-2">
        <button
          type="button"
          className={adminPrimaryButtonSmClass}
          disabled={!canSave}
          onClick={() => void save()}
        >
          {saving ? t("saving") : t("save")}
        </button>
        <button
          type="button"
          className="inline-flex min-h-11 items-center rounded-md border border-border px-3 text-sm"
          onClick={onClose}
        >
          {t("cancel")}
        </button>
        {presentation ? (
          <button
            type="button"
            className="inline-flex min-h-11 items-center px-3 text-sm text-danger underline"
            disabled={saving}
            onClick={() => void clearAll()}
          >
            {t("clearAll")}
          </button>
        ) : null}
      </div>
    </section>
  );
}
