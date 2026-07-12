"use client";

import { useTranslations } from "next-intl";
import { useState } from "react";

import { type FlagAction, type FlagQueueItem, flagsApi, flagActionPath } from "./api";

type FlagActionDialogProps = {
  item: FlagQueueItem;
  action: FlagAction;
  onClose: () => void;
  onComplete: () => void;
};

export function FlagActionDialog({ item, action, onClose, onComplete }: FlagActionDialogProps) {
  const t = useTranslations("admin.flags.actions");
  const tCommon = useTranslations("admin.flags.common");
  const [note, setNote] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const destructive = action === "remove" || action === "escalate-suspend";

  const submit = async () => {
    setSubmitting(true);
    setError(null);
    try {
      await flagsApi.request(flagActionPath(item.id, action), {
        method: "POST",
        body: JSON.stringify({ note: note.trim() || null }),
      });
      onComplete();
    } catch {
      setError(t("failure"));
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div
      className="fixed inset-0 z-50 flex items-end justify-center bg-black/40 p-4 sm:items-center"
      role="dialog"
      aria-modal="true"
      aria-labelledby="flag-action-title"
    >
      <div className="w-full max-w-md rounded-lg border border-border bg-surface p-4 shadow-lg">
        <h2 id="flag-action-title" className="font-serif text-lg text-text">
          {t(`${action}.title`)}
        </h2>
        <p className="mt-2 text-sm text-muted">{t(`${action}.body`)}</p>
        {destructive ? (
          <p className="mt-2 text-sm font-medium text-danger">{t(`${action}.warning`)}</p>
        ) : null}
        <label className="mt-4 block text-sm text-text">
          {tCommon("noteLabel")}
          <textarea
            className="mt-1 w-full rounded-md border border-border px-3 py-2 text-sm"
            rows={3}
            value={note}
            onChange={(event) => setNote(event.target.value)}
            placeholder={tCommon("notePlaceholder")}
          />
        </label>
        {error ? <p className="mt-2 text-sm text-danger">{error}</p> : null}
        <div className="mt-4 flex flex-wrap justify-end gap-2">
          <button
            type="button"
            className="inline-flex min-h-11 items-center rounded-md border border-border px-4 text-sm"
            onClick={onClose}
            disabled={submitting}
          >
            {tCommon("cancel")}
          </button>
          <button
            type="button"
            className={`inline-flex min-h-11 items-center rounded-md px-4 text-sm font-medium text-white ${
              destructive ? "bg-danger" : "bg-primary"
            }`}
            onClick={() => void submit()}
            disabled={submitting}
          >
            {submitting ? tCommon("submitting") : t(`${action}.confirm`)}
          </button>
        </div>
      </div>
    </div>
  );
}
