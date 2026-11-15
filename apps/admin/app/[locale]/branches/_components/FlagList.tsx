"use client";

import { useTranslations } from "next-intl";
import { useState } from "react";

import { branchesApi, decisionErrorKey, type BranchFlag } from "./api";

type FlagListProps = {
  flags: BranchFlag[];
  onResolved: () => void;
};

/** Duplicate-signal flags with clear / confirm actions (each audited by the API). */
export function FlagList({ flags, onResolved }: FlagListProps) {
  const t = useTranslations("admin");
  const [notes, setNotes] = useState<Record<string, string>>({});
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const resolve = async (flag: BranchFlag, resolution: "cleared" | "confirmed") => {
    const note = (notes[flag.id] ?? "").trim();
    if (note.length < 3) {
      setError("branches.errors.noteRequired");
      return;
    }
    setBusy(flag.id);
    setError(null);
    try {
      await branchesApi.request(`/admin/branches/flags/${flag.id}/resolve`, {
        method: "POST",
        body: JSON.stringify({ resolution, note }),
      });
      onResolved();
    } catch (err) {
      setError(decisionErrorKey(err));
    } finally {
      setBusy(null);
    }
  };

  if (flags.length === 0) {
    return <p className="m-0 text-sm text-muted">{t("branches.flags.none")}</p>;
  }

  return (
    <div className="space-y-2">
      {error ? (
        <p role="alert" className="m-0 text-sm text-danger">
          {t(error)}
        </p>
      ) : null}
      <ul className="m-0 list-none space-y-2 p-0">
        {flags.map((flag) => (
          <li key={flag.id} className="space-y-2 rounded-md border border-border bg-surface p-3">
            <p className="m-0 text-sm font-medium text-text">
              {t(`branches.flagKind.${flag.kind}`)} ·{" "}
              {t("branches.flags.score", { score: Math.round(flag.score * 100) })}
            </p>
            <p className="m-0 text-xs text-muted">
              {t("branches.flags.pair", {
                branch: flag.vendor_name ?? flag.vendor_id,
                matched: flag.matched_vendor_name ?? flag.matched_vendor_id ?? "—",
              })}
            </p>
            {flag.status === "open" ? (
              <div className="flex flex-wrap items-center gap-2">
                <input
                  aria-label={t("branches.flags.noteLabel")}
                  placeholder={t("branches.flags.notePlaceholder")}
                  className="min-h-11 flex-1 rounded-md border border-border bg-surface px-2 text-sm text-text"
                  value={notes[flag.id] ?? ""}
                  maxLength={1000}
                  onChange={(event) =>
                    setNotes((prev) => ({ ...prev, [flag.id]: event.target.value }))
                  }
                />
                {flag.kind !== "payout_other_owner" ? (
                  <button
                    type="button"
                    disabled={busy === flag.id}
                    className="inline-flex min-h-11 items-center rounded-md border border-border px-3 text-sm"
                    onClick={() => void resolve(flag, "cleared")}
                  >
                    {t("branches.flags.clear")}
                  </button>
                ) : null}
                <button
                  type="button"
                  disabled={busy === flag.id}
                  className="inline-flex min-h-11 items-center rounded-md bg-danger px-3 text-sm font-medium text-on-danger"
                  onClick={() => void resolve(flag, "confirmed")}
                >
                  {t("branches.flags.confirm")}
                </button>
              </div>
            ) : (
              <p className="m-0 text-xs text-muted">
                {t(`branches.flagStatus.${flag.status}`)}
                {flag.resolution_note ? ` · ${flag.resolution_note}` : ""}
              </p>
            )}
          </li>
        ))}
      </ul>
    </div>
  );
}
