"use client";

import { Button } from "@vergeo/ui/src/button";
import { Switch } from "@vergeo/ui/src/switch";
import { ThemePreference } from "@vergeo/ui/src/theme-preference";
import { useRouter } from "next/navigation";
import { useState } from "react";

import { LocaleSwitcher, type LocaleSwitcherLabels } from "../../_components/locale-switcher";

import { createAccountApiClient, type NotificationPrefs } from "./account-api";

export type PreferencesFormLabels = {
  themeTitle: string;
  themeDescription: string;
  themeLight: string;
  themeDark: string;
  themeSystem: string;
  notificationsTitle: string;
  whatsapp: string;
  whatsappHelp: string;
  sms: string;
  smsHelp: string;
  email: string;
  emailHelp: string;
  save: string;
  saving: string;
  saved: string;
  error: string;
};

type PreferencesFormProps = {
  accessToken: string;
  locale: string;
  initialPrefs: NotificationPrefs;
  labels: PreferencesFormLabels;
  localeSwitcherLabels: LocaleSwitcherLabels;
};

export function PreferencesForm({
  accessToken,
  locale,
  initialPrefs,
  labels,
  localeSwitcherLabels,
}: PreferencesFormProps) {
  const router = useRouter();
  const api = createAccountApiClient(() => accessToken);

  const [prefs, setPrefs] = useState(initialPrefs);
  const [saving, setSaving] = useState(false);
  const [status, setStatus] = useState<string | undefined>();
  const [error, setError] = useState<string | undefined>();

  const handleSubmit = async (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setSaving(true);
    setError(undefined);
    setStatus(undefined);

    try {
      const updated = await api.patchPreferences(prefs);
      setPrefs(updated.notif_prefs);
      setStatus(labels.saved);
      router.refresh();
    } catch {
      setError(labels.error);
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="space-y-8">
      <ThemePreference
        label={labels.themeTitle}
        description={labels.themeDescription}
        lightLabel={labels.themeLight}
        darkLabel={labels.themeDark}
        systemLabel={labels.themeSystem}
      />

      <section className="space-y-2">
        <h3 className="font-medium text-text">{localeSwitcherLabels.ariaLabel}</h3>
        <LocaleSwitcher locale={locale} labels={localeSwitcherLabels} variant="shop" />
      </section>

      <form className="space-y-5" onSubmit={(event) => void handleSubmit(event)}>
        <h3 className="font-medium text-text">{labels.notificationsTitle}</h3>
        <Switch
          id="pref-whatsapp"
          label={
            <span>
              <span className="block font-medium">{labels.whatsapp}</span>
              <span className="block text-sm text-text-2">{labels.whatsappHelp}</span>
            </span>
          }
          checked={prefs.whatsapp}
          onChange={(event) =>
            setPrefs((current) => ({ ...current, whatsapp: event.target.checked }))
          }
        />
        <Switch
          id="pref-sms"
          label={
            <span>
              <span className="block font-medium">{labels.sms}</span>
              <span className="block text-sm text-text-2">{labels.smsHelp}</span>
            </span>
          }
          checked={prefs.sms}
          onChange={(event) => setPrefs((current) => ({ ...current, sms: event.target.checked }))}
        />
        <Switch
          id="pref-email"
          label={
            <span>
              <span className="block font-medium">{labels.email}</span>
              <span className="block text-sm text-text-2">{labels.emailHelp}</span>
            </span>
          }
          checked={prefs.email}
          onChange={(event) => setPrefs((current) => ({ ...current, email: event.target.checked }))}
        />

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
    </div>
  );
}
