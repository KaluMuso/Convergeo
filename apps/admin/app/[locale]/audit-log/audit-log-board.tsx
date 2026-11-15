"use client";

import { useTranslations } from "next-intl";
import { useCallback, useEffect, useRef, useState } from "react";

import { rolesApi, useAdminPermissions } from "../../../lib/roles-api";

export type AuditEntry = {
  id: string;
  at: string;
  actor: string | null;
  actor_roles: string[] | null;
  action: string;
  entity_type: string;
  entity_id: string | null;
  outcome: "success" | "denied" | "failed" | string;
  request_id: string | null;
  reason: string | null;
  before: unknown;
  after: unknown;
};

type AuditPage = { items: AuditEntry[]; next_before: string | null };

export type AuditFilters = {
  actor: string;
  action: string;
  entityType: string;
  entityId: string;
  outcome: "" | "success" | "denied" | "failed";
  from: string;
  to: string;
};

const EMPTY_FILTERS: AuditFilters = {
  actor: "",
  action: "",
  entityType: "",
  entityId: "",
  outcome: "",
  from: "",
  to: "",
};

const UUID_RE = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

/** Build the read-only query string; invalid filters are reported, never sent. */
export function buildAuditQuery(
  filters: AuditFilters,
  before: string | null,
): { query: string } | { invalid: true } {
  const params = new URLSearchParams();
  if (filters.actor) {
    if (!UUID_RE.test(filters.actor)) return { invalid: true };
    params.set("actor", filters.actor);
  }
  if (filters.entityId) {
    if (!UUID_RE.test(filters.entityId)) return { invalid: true };
    params.set("entity_id", filters.entityId);
  }
  if (filters.action) {
    if (!/^[a-z0-9_.:-]{1,80}$/.test(filters.action)) return { invalid: true };
    params.set("action", filters.action);
  }
  if (filters.entityType) {
    if (!/^[a-z0-9_]{1,60}$/.test(filters.entityType)) return { invalid: true };
    params.set("entity_type", filters.entityType);
  }
  if (filters.outcome) params.set("outcome", filters.outcome);
  if (filters.from) params.set("from", new Date(`${filters.from}T00:00:00Z`).toISOString());
  if (filters.to) params.set("to", new Date(`${filters.to}T23:59:59Z`).toISOString());
  if (before) params.set("before", before);
  params.set("limit", "50");
  return { query: params.toString() };
}

export function AuditLogBoard({ locale }: { locale: string }) {
  const t = useTranslations("admin.auditLogUi");
  const grants = useAdminPermissions();
  const allowed = grants?.permissions.includes("audit.read") === true;
  const [draft, setDraft] = useState<AuditFilters>(EMPTY_FILTERS);
  const [filters, setFilters] = useState<AuditFilters>(EMPTY_FILTERS);
  const [items, setItems] = useState<AuditEntry[] | null>(null);
  const [nextBefore, setNextBefore] = useState<string | null>(null);
  const [error, setError] = useState<"" | "loadFailed" | "invalid">("");
  const [loading, setLoading] = useState(false);
  const generation = useRef(0);

  const load = useCallback(async (active: AuditFilters, before: string | null) => {
    const built = buildAuditQuery(active, before);
    if ("invalid" in built) {
      setError("invalid");
      return;
    }
    const current = ++generation.current;
    setLoading(true);
    setError("");
    try {
      const page = await rolesApi.request<AuditPage>(`/admin/audit-log?${built.query}`, {
        cache: "no-store",
      });
      if (current !== generation.current) return;
      if (!Array.isArray(page?.items)) throw new Error("Invalid audit page");
      setItems((previous) => (before && previous ? [...previous, ...page.items] : page.items));
      setNextBefore(page.next_before ?? null);
    } catch {
      if (current === generation.current) setError("loadFailed");
    } finally {
      if (current === generation.current) setLoading(false);
    }
  }, []);

  useEffect(() => {
    if (allowed) void load(filters, null);
  }, [allowed, filters, load]);

  if (!allowed) return <p role="alert">{t("permissionDenied")}</p>;

  const field = (key: keyof AuditFilters, label: string, type = "text") => (
    <label className="block text-sm">
      {label}
      <input
        type={type}
        value={draft[key]}
        onChange={(event) => setDraft({ ...draft, [key]: event.target.value })}
        className="min-h-11 w-full rounded border p-2"
      />
    </label>
  );

  return (
    <div className="space-y-6">
      <header className="space-y-1">
        <h1 className="font-serif text-xl">{t("title")}</h1>
        <p className="text-sm text-muted">{t("subtitle")}</p>
      </header>
      <form
        aria-label={t("filters")}
        className="grid gap-3 sm:grid-cols-2"
        onSubmit={(event) => {
          event.preventDefault();
          setItems(null);
          setFilters({ ...draft });
        }}
      >
        {field("actor", t("actor"))}
        {field("action", t("action"))}
        {field("entityType", t("resource"))}
        {field("entityId", t("resourceId"))}
        <label className="block text-sm">
          {t("outcome")}
          <select
            value={draft.outcome}
            onChange={(event) =>
              setDraft({ ...draft, outcome: event.target.value as AuditFilters["outcome"] })
            }
            className="min-h-11 w-full rounded border p-2"
          >
            <option value="">{t("outcomeAny")}</option>
            <option value="success">{t("outcomeSuccess")}</option>
            <option value="denied">{t("outcomeDenied")}</option>
            <option value="failed">{t("outcomeFailed")}</option>
          </select>
        </label>
        {field("from", t("from"), "date")}
        {field("to", t("to"), "date")}
        <div className="flex items-end gap-3">
          <button className="min-h-11 rounded bg-primary px-4 text-white" disabled={loading}>
            {t("apply")}
          </button>
          <button
            type="button"
            className="min-h-11 underline"
            onClick={() => {
              setDraft(EMPTY_FILTERS);
              setItems(null);
              setFilters(EMPTY_FILTERS);
            }}
          >
            {t("reset")}
          </button>
        </div>
      </form>
      <p className="text-xs text-muted">{t("maskingNote")}</p>
      {error ? (
        <p role="alert" className="text-error">
          {t(error)}
        </p>
      ) : null}
      {items === null ? (
        loading ? (
          <p role="status">{t("loading")}</p>
        ) : null
      ) : items.length === 0 ? (
        <p>{t("empty")}</p>
      ) : (
        <ul className="space-y-2">
          {items.map((entry) => (
            <li key={entry.id} className="rounded border p-3 text-sm">
              <p className="font-semibold">
                {entry.action} ·{" "}
                <span data-testid="audit-outcome">
                  {entry.outcome === "denied"
                    ? t("outcomeDenied")
                    : entry.outcome === "failed"
                      ? t("outcomeFailed")
                      : t("outcomeSuccess")}
                </span>
              </p>
              <p className="text-muted">
                {t("when", { at: new Date(entry.at).toLocaleString(locale) })}
              </p>
              <p className="text-muted">
                {t("who", {
                  actor: entry.actor ?? t("system"),
                  roles: (entry.actor_roles ?? []).join(", ") || t("noRoles"),
                })}
              </p>
              <p className="text-muted">
                {t("what", { resource: entry.entity_type, id: entry.entity_id ?? "—" })}
              </p>
              {entry.reason ? <p>{t("reason", { reason: entry.reason })}</p> : null}
              {entry.request_id ? (
                <p className="font-mono text-xs text-muted">
                  {t("requestId", { id: entry.request_id })}
                </p>
              ) : null}
              <details className="mt-1">
                <summary className="min-h-11 cursor-pointer">{t("details")}</summary>
                <pre className="overflow-x-auto whitespace-pre-wrap break-all text-xs">
                  {JSON.stringify({ before: entry.before, after: entry.after }, null, 2)}
                </pre>
              </details>
            </li>
          ))}
        </ul>
      )}
      {nextBefore ? (
        <button
          className="min-h-11 underline"
          disabled={loading}
          onClick={() => void load(filters, nextBefore)}
        >
          {t("more")}
        </button>
      ) : null}
    </div>
  );
}
