"use client";

import { notify } from "@vergeo/ui/src/toast";
import { useTranslations } from "next-intl";
import { useCallback, useEffect, useState } from "react";

import { useAdminPermissions } from "../../../../lib/roles-api";
import { AdminLoadFailure } from "../../_components/AdminLoadFailure";
import { classifyAdminRequestError } from "../../_components/admin-request";
import { ConfirmModal } from "../../_components/ConfirmModal";
import { CopyButton } from "../../_components/CopyButton";
import { EmptyBlock, LoadingBlock } from "../../_components/StateBlocks";

import {
  actionsFor,
  canAccessTab,
  catalogApi,
  catalogPath,
  CATALOG_TABS,
  isValidReason,
  type CatalogAction,
  type CatalogEntity,
  type CatalogTab,
} from "./catalog-api";

const CUSTOMER_ORIGIN = process.env.NEXT_PUBLIC_VERGEO_CUSTOMER_URL ?? "http://localhost:3000";

const inputClass = "min-h-11 w-full rounded-md border border-border bg-bg px-3 text-sm text-text";
const buttonClass =
  "inline-flex min-h-11 items-center rounded-md border border-border px-3 text-xs font-medium text-text";

type Pending = { entity: CatalogEntity; action: CatalogAction } | null;
type LoadState =
  | { kind: "loading" }
  | { kind: "error"; permission: boolean }
  | { kind: "ready"; rows: CatalogEntity[] };

export function CatalogControlBoard({ locale }: { locale: string }) {
  const t = useTranslations("admin.catalog");
  const grants = useAdminPermissions();
  const [tab, setTab] = useState<CatalogTab>("listings");
  const [query, setQuery] = useState("");
  const [submittedQuery, setSubmittedQuery] = useState("");
  const [heldOnly, setHeldOnly] = useState(false);
  const [state, setState] = useState<LoadState>({ kind: "loading" });
  const [pending, setPending] = useState<Pending>(null);
  const [reason, setReason] = useState("");
  const [title, setTitle] = useState("");
  const [description, setDescription] = useState("");
  const [actionError, setActionError] = useState<string | null>(null);

  const canRead = canAccessTab(tab, grants, "read");
  const canWrite = canAccessTab(tab, grants, "write");

  const load = useCallback(async () => {
    setState({ kind: "loading" });
    try {
      const rows = await catalogApi.request<CatalogEntity[]>(
        catalogPath(tab, submittedQuery, heldOnly),
        { cache: "no-store" },
      );
      setState({ kind: "ready", rows: Array.isArray(rows) ? rows : [] });
    } catch (error) {
      setState({
        kind: "error",
        permission: classifyAdminRequestError(error).kind === "permission",
      });
    }
  }, [tab, submittedQuery, heldOnly]);

  useEffect(() => {
    if (grants && !canRead) {
      setState({ kind: "error", permission: true });
      return;
    }
    if (grants) void load();
  }, [grants, canRead, load]);

  const open = (entity: CatalogEntity, action: CatalogAction) => {
    setPending({ entity, action });
    setReason("");
    setTitle(entity.label);
    setDescription("");
    setActionError(null);
  };

  const run = async (): Promise<boolean> => {
    if (!pending) return false;
    const { entity, action } = pending;
    const base = `/admin/catalog/${tab}/${entity.id}`;
    try {
      if (action === "edit") {
        await catalogApi.request(base, {
          method: "PATCH",
          body: JSON.stringify({
            title: title.trim() && title.trim() !== entity.label ? title.trim() : undefined,
            description: description.trim() || undefined,
            reason: reason.trim(),
          }),
        });
      } else if (action === "restore") {
        await catalogApi.request(`${base}/restore`, {
          method: "POST",
          body: JSON.stringify({ reason: reason.trim() }),
        });
      } else {
        await catalogApi.request(`${base}/moderate`, {
          method: "POST",
          body: JSON.stringify({ action, reason: reason.trim() }),
        });
      }
      notify.success(t(`done.${action}`));
      await load();
      return true;
    } catch (error) {
      const failure = classifyAdminRequestError(error);
      const status = (error as { status?: number } | null)?.status;
      setActionError(
        failure.kind === "permission"
          ? t("errors.permission")
          : status === 409 || status === 404
            ? t("errors.conflict")
            : t("errors.generic"),
      );
      return false;
    }
  };

  const summaryKey = (entity: CatalogEntity, action: CatalogAction) => {
    if (action === "block" && tab === "vendors") return "confirm.blockVendorSummary";
    if (action === "restore" && tab === "vendors") return "confirm.restoreVendorSummary";
    return `confirm.${action}Summary`;
  };

  const editHasChange =
    pending?.action !== "edit" ||
    (title.trim().length >= 2 && title.trim() !== pending.entity.label) ||
    description.trim().length > 0;

  return (
    <div className="space-y-4">
      <div role="tablist" aria-label={t("title")} className="flex flex-wrap gap-2">
        {CATALOG_TABS.map((key) => (
          <button
            key={key}
            type="button"
            role="tab"
            aria-selected={tab === key}
            className={`${buttonClass} ${tab === key ? "border-primary bg-primary/10" : ""}`}
            onClick={() => setTab(key)}
          >
            {t(`tabs.${key}`)}
          </button>
        ))}
      </div>

      <form
        className="flex flex-wrap items-end gap-2"
        onSubmit={(event) => {
          event.preventDefault();
          setSubmittedQuery(query);
        }}
      >
        <label className="min-w-0 flex-1 space-y-1 text-sm">
          <span className="text-muted">{t("search")}</span>
          <input
            className={inputClass}
            value={query}
            maxLength={80}
            onChange={(event) => setQuery(event.target.value)}
          />
        </label>
        <button type="submit" className={buttonClass}>
          {t("searchButton")}
        </button>
        <label className="flex min-h-11 items-center gap-2 text-sm text-text">
          <input
            type="checkbox"
            checked={heldOnly}
            onChange={(event) => setHeldOnly(event.target.checked)}
          />
          {t("heldOnly")}
        </label>
      </form>

      {state.kind === "loading" ? (
        <LoadingBlock label={t("loading")} />
      ) : state.kind === "error" ? (
        <AdminLoadFailure
          permissionDenied={state.permission}
          message={state.permission ? t("permissionDenied") : t("loadError")}
          hint={state.permission ? t("permissionHint") : undefined}
          retryLabel={t("retry")}
          onRetry={() => void load()}
        />
      ) : state.rows.length === 0 ? (
        <EmptyBlock title={t("empty")} body={t("emptyBody")} />
      ) : (
        <ul className="space-y-2" data-testid="catalog-rows">
          {state.rows.map((entity) => (
            <li
              key={entity.id}
              className="space-y-2 rounded-md border border-border bg-surface p-3 text-sm"
            >
              <div className="flex flex-wrap items-start justify-between gap-2">
                <div className="min-w-0 space-y-1">
                  <p className="font-medium text-text">{entity.label}</p>
                  <p className="text-xs text-muted">
                    {t("statusLabel", { status: entity.status })}
                  </p>
                  <span
                    className={`inline-flex rounded-full px-2 py-0.5 text-xs font-medium ${
                      entity.visible ? "bg-success/10 text-success" : "bg-warning/10 text-warning"
                    }`}
                  >
                    {entity.visible ? t("visible") : t("notVisible")}
                  </span>
                  {entity.hold ? (
                    <p className="text-xs text-text-2">
                      {t("heldBy", { action: entity.hold.action, reason: entity.hold.reason })}
                    </p>
                  ) : !entity.visible && entity.status === "active" && tab !== "vendors" ? (
                    <p className="text-xs text-text-2">{t("vendorSuspendedNote")}</p>
                  ) : null}
                </div>
                <div className="flex flex-wrap items-center gap-2">
                  <CopyButton value={entity.id} label={t("copyId")} />
                  {entity.visible ? (
                    <a
                      className={buttonClass}
                      href={`${CUSTOMER_ORIGIN}/${locale}${entity.href}`}
                      target="_blank"
                      rel="noopener noreferrer"
                    >
                      {t("open")}
                    </a>
                  ) : null}
                </div>
              </div>
              {canWrite ? (
                <div className="flex flex-wrap gap-2">
                  {actionsFor(tab, entity).map((action) => (
                    <button
                      key={action}
                      type="button"
                      className={`${buttonClass} ${action === "block" ? "border-danger text-danger" : ""}`}
                      onClick={() => open(entity, action)}
                    >
                      {t(`actions.${action}`)}
                    </button>
                  ))}
                </div>
              ) : null}
            </li>
          ))}
        </ul>
      )}

      {pending ? (
        <ConfirmModal
          open
          data-testid="catalog-confirm"
          title={t(`confirm.${pending.action}Title`)}
          summary={t(summaryKey(pending.entity, pending.action), { label: pending.entity.label })}
          confirmLabel={t(
            `confirm.confirm${pending.action.charAt(0).toUpperCase()}${pending.action.slice(1)}`,
          )}
          destructive={pending.action === "block"}
          canConfirm={isValidReason(reason) && editHasChange}
          error={actionError}
          onConfirm={run}
          onClose={() => setPending(null)}
        >
          <div className="space-y-3">
            {pending.action === "edit" ? (
              <>
                <label className="block space-y-1 text-sm">
                  <span>{t("confirm.titleLabel")}</span>
                  <input
                    className={inputClass}
                    value={title}
                    maxLength={160}
                    onChange={(event) => setTitle(event.target.value)}
                  />
                </label>
                <label className="block space-y-1 text-sm">
                  <span>{t("confirm.descriptionLabel")}</span>
                  <textarea
                    className={`${inputClass} min-h-20 py-2`}
                    value={description}
                    maxLength={5000}
                    onChange={(event) => setDescription(event.target.value)}
                  />
                </label>
              </>
            ) : null}
            <label className="block space-y-1 text-sm">
              <span>{t("confirm.reasonLabel")}</span>
              <textarea
                className={`${inputClass} min-h-16 py-2`}
                required
                maxLength={500}
                value={reason}
                placeholder={t("confirm.reasonPlaceholder")}
                onChange={(event) => setReason(event.target.value)}
              />
            </label>
          </div>
        </ConfirmModal>
      ) : null}
    </div>
  );
}
