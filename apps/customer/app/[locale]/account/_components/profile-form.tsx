"use client";

import { LOCALES } from "@vergeo/i18n";
import { Button } from "@vergeo/ui/src/button";
import { FormField } from "@vergeo/ui/src/form-field";
import { Input } from "@vergeo/ui/src/input";
import { Select } from "@vergeo/ui/src/select";
import { useRouter } from "next/navigation";
import { useState } from "react";

import { createAccountApiClient, type Profile } from "./account-api";

export type ProfileFormLabels = {
  nameLabel: string;
  namePlaceholder: string;
  localeLabel: string;
  phoneLabel: string;
  phoneHelp: string;
  save: string;
  saving: string;
  updated: string;
  error: string;
  locales: Record<string, string>;
};

type ProfileFormProps = {
  locale: string;
  accessToken: string;
  initialProfile: Profile;
  labels: ProfileFormLabels;
};

export function ProfileForm({ locale, accessToken, initialProfile, labels }: ProfileFormProps) {
  const router = useRouter();
  const api = createAccountApiClient(() => accessToken);

  const [displayName, setDisplayName] = useState(initialProfile.display_name ?? "");
  const [selectedLocale, setSelectedLocale] = useState(initialProfile.locale);
  const [saving, setSaving] = useState(false);
  const [status, setStatus] = useState<string | undefined>();
  const [error, setError] = useState<string | undefined>();

  const handleSubmit = async (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setError(undefined);
    setStatus(undefined);
    setSaving(true);

    try {
      const updated = await api.patchProfile({
        display_name: displayName.trim() || null,
        locale: selectedLocale,
      });
      const name = updated.display_name ?? labels.namePlaceholder;
      setStatus(labels.updated.replace("{name}", name));

      if (updated.locale !== locale) {
        window.location.assign(`/${updated.locale}/account`);
        return;
      }

      router.refresh();
    } catch {
      setError(labels.error);
    } finally {
      setSaving(false);
    }
  };

  return (
    <form className="space-y-4" onSubmit={(event) => void handleSubmit(event)}>
      <FormField label={labels.nameLabel}>
        <Input
          value={displayName}
          onChange={(event) => setDisplayName(event.target.value)}
          placeholder={labels.namePlaceholder}
          autoComplete="name"
        />
      </FormField>

      <FormField label={labels.localeLabel}>
        <Select
          value={selectedLocale}
          onChange={(event) => setSelectedLocale(event.target.value)}
          aria-label={labels.localeLabel}
        >
          {LOCALES.map((code) => (
            <option key={code} value={code}>
              {labels.locales[code] ?? code}
            </option>
          ))}
        </Select>
      </FormField>

      <FormField label={labels.phoneLabel} helpText={labels.phoneHelp}>
        <Input value={initialProfile.phone ?? ""} disabled readOnly aria-readonly="true" />
      </FormField>

      {status ? (
        <p className="text-sm text-success" role="status">
          {status}
        </p>
      ) : null}
      {error ? (
        <p className="text-sm text-danger" role="alert">
          {error}
        </p>
      ) : null}

      <Button type="submit" loading={saving} loadingLabel={labels.saving}>
        {labels.save}
      </Button>
    </form>
  );
}
