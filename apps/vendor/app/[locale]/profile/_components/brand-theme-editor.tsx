"use client";

import {
  contrastRatio,
  ensureContrast,
  extractBrandTheme,
  isHexColor,
  type BrandTheme,
} from "@vergeo/ui/src/brand-theme";
import { useTranslations } from "next-intl";
import { useState } from "react";

type BrandThemeEditorProps = {
  value: BrandTheme;
  onChange: (next: BrandTheme) => void;
  logoUrl: string | null;
  disabled?: boolean;
};

const MIN = { primary: 4.5, accent: 3 } as const;

/** Read logo pixels through a small canvas (Cloudinary serves CORS-enabled images). */
async function readLogoPixels(url: string): Promise<Uint8ClampedArray> {
  const image = new Image();
  image.crossOrigin = "anonymous";
  const sized = url.includes("/upload/")
    ? url.replace("/upload/", "/upload/w_96,h_96,c_fit/")
    : url;
  await new Promise<void>((resolve, reject) => {
    image.onload = () => resolve();
    image.onerror = () => reject(new Error("logo"));
    image.src = sized;
  });
  const canvas = document.createElement("canvas");
  canvas.width = 96;
  canvas.height = 96;
  const context = canvas.getContext("2d");
  if (!context) {
    throw new Error("canvas");
  }
  context.drawImage(image, 0, 0, 96, 96);
  return context.getImageData(0, 0, 96, 96).data;
}

/**
 * Storefront brand colours: pick primary + accent, or derive them from the
 * uploaded logo (client-side colour quantisation, no external service). Both
 * are clamped to WCAG AA as you pick; the API clamps again before storing.
 */
export function BrandThemeEditor({
  value,
  onChange,
  logoUrl,
  disabled,
}: BrandThemeEditorProps) {
  const t = useTranslations("vendor.profile.brand");
  const [extracting, setExtracting] = useState(false);
  const [extractError, setExtractError] = useState(false);
  const [adjusted, setAdjusted] = useState<null | "primary" | "accent">(null);

  const setField = (key: "primary" | "accent", raw: string) => {
    if (!isHexColor(raw)) {
      onChange({ ...value, [key]: raw === "" ? null : value[key] });
      return;
    }
    const clamped = ensureContrast(raw.toUpperCase(), MIN[key]);
    setAdjusted(clamped !== raw.toUpperCase() ? key : null);
    onChange({ ...value, [key]: clamped });
  };

  const extract = async () => {
    if (!logoUrl) {
      return;
    }
    setExtracting(true);
    setExtractError(false);
    try {
      const theme = extractBrandTheme(await readLogoPixels(logoUrl));
      if (theme) {
        onChange(theme);
      } else {
        setExtractError(true);
      }
    } catch {
      setExtractError(true);
    } finally {
      setExtracting(false);
    }
  };

  const fields = [
    { key: "primary" as const, label: t("primary"), help: t("primaryHelp") },
    { key: "accent" as const, label: t("accent"), help: t("accentHelp") },
  ];

  return (
    <div className="space-y-3" data-testid="brand-theme-editor">
      <p className="text-sm text-text-2">{t("help")}</p>
      <div className="grid gap-3 sm:grid-cols-2">
        {fields.map((field) => {
          const current = value[field.key];
          const ratio = current ? contrastRatio(current, "#FFFFFF") : null;
          return (
            <label
              key={field.key}
              className="flex items-center gap-3 rounded border border-border p-3"
            >
              <input
                type="color"
                aria-label={field.label}
                value={current ?? "#0B5D45"}
                disabled={disabled}
                onChange={(event) => setField(field.key, event.target.value)}
                className="h-11 w-11 shrink-0 cursor-pointer rounded border-0 bg-transparent p-0"
              />
              <span className="min-w-0 flex-1">
                <span className="block text-sm font-semibold text-text">
                  {field.label}
                </span>
                <span className="block text-xs text-text-3">
                  {current
                    ? `${current} · ${t("contrast", { ratio: (ratio ?? 0).toFixed(1) })}`
                    : field.help}
                </span>
              </span>
              {current ? (
                <button
                  type="button"
                  className="min-h-11 shrink-0 px-2 text-sm text-text-2 hover:text-text"
                  onClick={() => onChange({ ...value, [field.key]: null })}
                  disabled={disabled}
                >
                  {t("reset")}
                </button>
              ) : null}
            </label>
          );
        })}
      </div>
      {adjusted ? (
        <p className="text-xs text-text-2" role="status">
          {t("adjusted")}
        </p>
      ) : null}
      <div className="flex flex-wrap items-center gap-3">
        <button
          type="button"
          onClick={() => void extract()}
          disabled={disabled || !logoUrl || extracting}
          data-testid="brand-extract"
          className="inline-flex min-h-11 items-center rounded-pill border border-border px-4 text-sm font-semibold text-text hover:border-primary disabled:opacity-50"
        >
          {extracting ? t("extracting") : t("extract")}
        </button>
        {!logoUrl ? (
          <span className="text-xs text-text-3">{t("needLogo")}</span>
        ) : null}
        {extractError ? (
          <span className="text-xs text-danger" role="alert">
            {t("extractFailed")}
          </span>
        ) : null}
      </div>
      {/* Live preview of a storefront button and accent mark. */}
      <div className="flex items-center gap-3 rounded bg-bg-2 p-3" aria-hidden>
        <span
          className="inline-flex min-h-10 items-center rounded px-4 text-sm font-semibold text-white"
          style={{ backgroundColor: value.primary ?? "var(--primary)" }}
        >
          {t("previewButton")}
        </span>
        <span
          className="text-sm font-bold"
          style={{ color: value.accent ?? "var(--accent)" }}
        >
          {t("previewAccent")}
        </span>
      </div>
    </div>
  );
}
