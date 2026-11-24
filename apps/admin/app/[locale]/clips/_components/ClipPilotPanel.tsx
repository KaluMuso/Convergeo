"use client";

import { useTranslations } from "next-intl";
import { useCallback, useEffect, useState } from "react";

import { AdminLoadFailure } from "../../_components/AdminLoadFailure";
import { resolveQueueLoadFailure } from "../../_components/queue-load-failure";

import { adminClipsApi, type ClipPilotState } from "./api";
import { PILOT_NOTE_MAX, pilotPosture, validatePilotAdd } from "./pilot";

/**
 * Clips pilot allowlist control.
 *
 * Authz, validation and the audit row all live on the API
 * (`/admin/clip-pilot`); this panel only explains and submits. The enforcement
 * switch is shown read-only on purpose — ending the pilot is a config change
 * with its own audit trigger, not a button beside the vendor list
 * (docs/ops/clips-pilot-enablement.md).
 */
export function ClipPilotPanel() {
  const t = useTranslations("admin.clips.pilot");
  const tRoot = useTranslations("admin.clips");
  const [data, setData] = useState<ClipPilotState | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [permissionDenied, setPermissionDenied] = useState(false);
  const [vendorId, setVendorId] = useState("");
  const [note, setNote] = useState("");
  const [formError, setFormError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    setPermissionDenied(false);
    try {
      setData(await adminClipsApi.pilot());
    } catch (err) {
      const failure = resolveQueueLoadFailure(err);
      setPermissionDenied(failure.permissionDenied);
      setError(t("loadFailed"));
    } finally {
      setLoading(false);
    }
  }, [t]);

  useEffect(() => {
    void load();
  }, [load]);

  const onAdd = useCallback(async () => {
    if (!data) return;
    const verdict = validatePilotAdd(
      vendorId,
      note,
      data.vendors.map((v) => v.vendor_id),
      data.max_vendors,
    );
    if (!verdict.ok) {
      setFormError(t(verdict.errorKey));
      return;
    }
    setBusy(true);
    setFormError(null);
    try {
      await adminClipsApi.addPilotVendor(verdict.vendorId, note.trim());
      setVendorId("");
      setNote("");
      await load();
    } catch {
      setFormError(t("errors.addFailed"));
    } finally {
      setBusy(false);
    }
  }, [data, vendorId, note, load, t]);

  const onRemove = useCallback(
    async (id: string) => {
      setBusy(true);
      try {
        await adminClipsApi.removePilotVendor(id);
        await load();
      } catch {
        setFormError(t("errors.removeFailed"));
      } finally {
        setBusy(false);
      }
    },
    [load, t],
  );

  if (loading) {
    return (
      <p className="text-sm text-muted" data-testid="clip-pilot-loading">
        {tRoot("loading")}
      </p>
    );
  }

  if (error && !data) {
    return (
      <AdminLoadFailure
        permissionDenied={permissionDenied}
        message={error}
        retryLabel={tRoot("error.retry")}
        onRetry={() => void load()}
      />
    );
  }

  if (!data) return null;

  const posture = pilotPosture(data);

  return (
    <section className="flex flex-col gap-6" data-testid="clip-pilot">
      <div className="flex flex-col gap-1 rounded-2 border border-border bg-surface p-4">
        <h2 className="text-sm font-medium text-text">{t("statusTitle")}</h2>
        <p
          className={posture === "pilot" ? "text-sm text-success" : "text-sm text-text"}
          data-testid={`clip-pilot-posture-${posture}`}
        >
          {t(`posture.${posture}`)}
        </p>
        <p className="text-xs text-muted">
          {data.comments_flag_enabled && posture === "pilot"
            ? t("commentsHeldOff")
            : t("commentsOff")}
        </p>
      </div>

      <div className="flex flex-col gap-3 rounded-2 border border-border bg-surface p-4">
        <h2 className="text-sm font-medium text-text">
          {t("listTitle", { count: data.vendors.length, max: data.max_vendors })}
        </h2>
        {data.vendors.length === 0 ? (
          <p className="text-sm text-muted" data-testid="clip-pilot-empty">
            {t("empty")}
          </p>
        ) : (
          <ul className="flex flex-col gap-2">
            {data.vendors.map((v) => (
              <li
                key={v.vendor_id}
                className="flex flex-wrap items-center justify-between gap-2 border-b border-border pb-2"
                data-testid="clip-pilot-vendor"
              >
                <div className="flex min-w-0 flex-col">
                  <span className="text-sm text-text">{v.vendor_name ?? v.vendor_id}</span>
                  <span className="break-all text-xs text-muted">{v.vendor_id}</span>
                  {v.vendor_status && v.vendor_status !== "active" ? (
                    <span className="text-xs text-danger">
                      {t("notActive", { status: v.vendor_status })}
                    </span>
                  ) : null}
                  {v.note ? <span className="text-xs text-muted">{v.note}</span> : null}
                </div>
                <button
                  type="button"
                  disabled={busy}
                  onClick={() => void onRemove(v.vendor_id)}
                  className="tap min-h-11 rounded-full border border-danger bg-surface px-4 py-2 text-sm text-danger disabled:opacity-50"
                  data-testid="clip-pilot-remove"
                >
                  {t("remove")}
                </button>
              </li>
            ))}
          </ul>
        )}
      </div>

      <form
        className="flex flex-col gap-2 rounded-2 border border-border bg-surface p-4"
        onSubmit={(event) => {
          event.preventDefault();
          void onAdd();
        }}
      >
        <h2 className="text-sm font-medium text-text">{t("addTitle")}</h2>
        <label className="flex flex-col gap-1 text-sm text-text">
          {t("vendorIdLabel")}
          <input
            value={vendorId}
            onChange={(event) => setVendorId(event.target.value)}
            inputMode="text"
            autoComplete="off"
            className="min-h-11 rounded-2 border border-border bg-bg px-3 text-sm text-text"
            data-testid="clip-pilot-vendor-id"
          />
        </label>
        <label className="flex flex-col gap-1 text-sm text-text">
          {t("noteLabel")}
          <input
            value={note}
            maxLength={PILOT_NOTE_MAX}
            onChange={(event) => setNote(event.target.value)}
            className="min-h-11 rounded-2 border border-border bg-bg px-3 text-sm text-text"
          />
        </label>
        <p className="text-xs text-muted">{t("addHelp")}</p>
        {formError ? (
          <p role="alert" className="text-sm text-danger" data-testid="clip-pilot-error">
            {formError}
          </p>
        ) : null}
        <button
          type="submit"
          disabled={busy}
          className="tap w-fit min-h-11 rounded-full bg-primary px-4 py-2 text-sm font-medium text-surface disabled:opacity-50"
          data-testid="clip-pilot-add"
        >
          {t("add")}
        </button>
      </form>
    </section>
  );
}
