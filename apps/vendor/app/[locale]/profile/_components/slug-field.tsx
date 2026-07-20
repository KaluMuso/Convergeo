"use client";

import { useTranslations } from "next-intl";

import { FormField, Input } from "../../listings/new/_lib/ui";

type SlugFieldProps = {
  slug: string;
  slugLocked: boolean;
  previousSlug: string | null;
  disabled: boolean;
  onChange: (value: string) => void;
};

export function SlugField({ slug, slugLocked, previousSlug, disabled, onChange }: SlugFieldProps) {
  const t = useTranslations("vendor");

  return (
    <div className="space-y-2">
      <FormField label={t("profile.fields.slugLabel")}>
        <Input
          name="slug"
          value={slug}
          onChange={(event) => onChange(event.target.value.toLowerCase())}
          disabled={disabled || slugLocked}
          autoComplete="off"
          spellCheck={false}
          placeholder={t("profile.fields.slugPlaceholder")}
        />
      </FormField>
      {slugLocked ? (
        <p className="text-sm text-text-2">{t("profile.slug.locked")}</p>
      ) : (
        <p className="text-sm text-warning">{t("profile.slug.onceWarning")}</p>
      )}
      {previousSlug ? (
        <p className="text-xs text-text-2">{t("profile.slug.previous", { slug: previousSlug })}</p>
      ) : null}
    </div>
  );
}
