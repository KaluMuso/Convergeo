"use client";

import { Button } from "@vergeo/ui/src/button";
import { Switch } from "@vergeo/ui/src/switch";
import { useRouter } from "next/navigation";
import { useState } from "react";

import { createAccountApiClient, type NotificationPrefs } from "./account-api";

export type PreferencesFormLabels = {
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
  initialPrefs: NotificationPrefs;
  labels: PreferencesFormLabels;
};

export function PreferencesForm({ accessToken, initialPrefs, labels }: PreferencesFormProps) {
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
    <form className="space-y-5" onSubmit={(event) => void handleSubmit(event)}>
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
  );
}
