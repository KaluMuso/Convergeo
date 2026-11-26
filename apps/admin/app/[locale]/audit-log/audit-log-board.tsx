"use client";

import { useTranslations } from "next-intl";
import { useCallback, useEffect, useRef, useState } from "react";

import { rolesApi, useAdminPermissions } from "../../../lib/roles-api";
import { adminPrimaryButtonClass } from "../_components/admin-primary-button";
import { CopyButton } from "../_components/CopyButton";
import { EmptyBlock } from "../_components/StateBlocks";

export type AuditEntry = {
  id: string;
  at: string;
  actor: string | null;
  actor_name?: string | null;
  actor_email?: string | null;
  actor_roles: string[] | null;
  action: string;
  entity_type: string;
  entity_id: string | null;
  entity_label?: string | null;
  outcome: "success" | "denied" | "failed" | string;
  request_id: string | null;
  reason: string | null;
  before: unknown;
  after: unknown;
};

/** Text-keyed resources (feature flags, config keys) store their name as `entity_key`. */
export function entityKey(entry: AuditEntry): string | null {
  for (const side of [entry.after, entry.before]) {
    if (side && typeof side === "object" && "entity_key" in side) {
      const key = (side as { entity_key?: unknown }).entity_key;
      if (typeof key === "string" && key) return key;
    }
  }
  return null;
}

type AuditPage = {
  items: AuditEntry[];
  next_before: string | null;
  next_before_id?: string | null;
};

export type DiffRow = { key: string; before: unknown; after: unknown };

const MAX_DIFF_DEPTH = 3;

function isPlainObject(value: unknown): value is Record<string, unknown> {
  return !!value && typeof value === "object" && !Array.isArray(value);
}

/** Changed leaves between before/after, keyed by dotted path (nested objects up to 3 levels). */
export function diffRows(before: unknown, after: unknown, prefix = "", depth = 0): DiffRow[] {
  if (depth < MAX_DIFF_DEPTH && (isPlainObject(before) || isPlainObject(after))) {
    const left = isPlainObject(before) ? before : {};
    const right = isPlainObject(after) ? after : {};
    if ((before != null && !isPlainObject(before)) || (after != null && !isPlainObject(after))) {
      return [{ key: prefix || "value", before, after }];
    }
    const keys = [...new Set([...Object.keys(left), ...Object.keys(right)])].sort();
    return keys.flatMap((key) =>
      diffRows(left[key], right[key], prefix ? `${prefix}.${key}` : key, depth + 1),
    );
  }
  if (JSON.stringify(before) === JSON.stringify(after)) return [];
  return [{ key: prefix || "value", before, after }];
}

export function formatDiffValue(value: unknown): string {
  if (value === undefined) return "";
  if (typeof value === "string") return value;
  return JSON.stringify(value);
}

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
  cursor: { before: string; beforeId: string } | null,
): { query: string } | { invalid: true } {
  const params = new URLSearchParams();
  const actor = filters.actor.trim();
  if (actor) {
    if (UUID_RE.test(actor)) params.set("actor", actor);
    else if (actor.length >= 2 && actor.length <= 80) params.set("actor_q", actor);
    else return { invalid: true };
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
  if (cursor) {
    params.set("before", cursor.before);
    params.set("before_id", cursor.beforeId);
  }
  params.set("limit", "50");
  return { query: params.toString() };
}

export function AuditLogBoard({ locale }: { locale: string }) {
  const t = useTranslations("admin.auditLogUi");
  const grants = useAdminPermissions();
  const allowed = !!grants && (grants.unrestricted || grants.permissions.includes("audit.read"));
  const [draft, setDraft] = useState<AuditFilters>(EMPTY_FILTERS);
  const [filters, setFilters] = useState<AuditFilters>(EMPTY_FILTERS);
  const [items, setItems] = useState<AuditEntry[] | null>(null);
  const [nextCursor, setNextCursor] = useState<{ before: string; beforeId: string } | null>(
    null,
  );
  const [error, setError] = useState<"" | "loadFailed" | "invalid">("");
  const [loading, setLoading] = useState(true);
  const generation = useRef(0);

  const load = useCallback(
    async (active: AuditFilters, cursor: { before: string; beforeId: string } | null) => {
    const built = buildAuditQuery(active, cursor);
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
      setItems((previous) => (cursor && previous ? [...previous, ...page.items] : page.items));
      setNextCursor(
        page.next_before && page.next_before_id
          ? { before: page.next_before, beforeId: page.next_before_id }
          : null,
      );
    } catch {
      if (current === generation.current) {
        setError("loadFailed");
        setItems([]);
      }
    } finally {
      if (current === generation.current) setLoading(false);
    }
  },
  [],
);

  useEffect(() => {
    if (grants === null) {
      return;
    }
    if (!allowed) {
      setLoading(false);
      setItems([]);
      return;
    }
    void load(filters, null);
  }, [allowed, filters, grants, load]);

  if (grants === null) {
    return <p role="status">{t("loadingGrants")}</p>;
  }

  if (!allowed) {
    return <p role="alert">{t("permissionDenied")}</p>;
  }

  const field = (key: keyof AuditFilters, label: string, type = "text", placeholder?: string) => (
    <label className="block text-sm">
      {label}
      <input
        type={type}
        value={draft[key]}
        placeholder={placeholder}
        onChange={(event) => setDraft({ ...draft, [key]: event.target.value })}
        className="min-h-11 w-full rounded-md border border-border bg-surface p-2"
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
        className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4"
        onSubmit={(event) => {
          event.preventDefault();
          setItems(null);
          setFilters({ ...draft });
        }}
      >
        {field("actor", t("actor"), "search", t("actorPlaceholder"))}
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
            className="min-h-11 w-full rounded-md border border-border bg-surface p-2"
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
          <button type="submit" className={adminPrimaryButtonClass} disabled={loading}>
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
        <p role="alert" className="text-danger">
          {t(error)}
        </p>
      ) : null}
      {loading && items === null ? (
        <p role="status">{t("loading")}</p>
      ) : items === null ? (
        <EmptyBlock title={t("loadFailedTitle")} body={t("loadFailedBody")} />
      ) : items.length === 0 ? (
        <EmptyBlock title={t("emptyTitle")} body={t("empty")} />
      ) : (
        <div className="overflow-x-auto rounded-lg border border-border bg-surface">
          <table className="w-full text-left text-sm" data-testid="audit-table">
            <thead className="border-b border-border text-xs text-muted">
              <tr>
                <th scope="col" className="px-3 py-2 font-medium">
                  {t("colWhen")}
                </th>
                <th scope="col" className="px-3 py-2 font-medium">
                  {t("colWho")}
                </th>
                <th scope="col" className="px-3 py-2 font-medium">
                  {t("colAction")}
                </th>
                <th scope="col" className="px-3 py-2 font-medium">
                  {t("colResource")}
                </th>
                <th scope="col" className="px-3 py-2 font-medium">
                  {t("outcome")}
                </th>
              </tr>
            </thead>
            {items.map((entry) => (
              <AuditRow key={entry.id} entry={entry} locale={locale} />
            ))}
          </table>
        </div>
      )}
      {nextCursor ? (
        <button
          className="min-h-11 underline"
          disabled={loading}
          onClick={() => void load(filters, nextCursor)}
        >
          {t("more")}
        </button>
      ) : null}
    </div>
  );
}

function AuditRow({ entry, locale }: { entry: AuditEntry; locale: string }) {
  const t = useTranslations("admin.auditLogUi");
  const changes = diffRows(entry.before, entry.after);
  const resourceId = entry.entity_id ?? entityKey(entry);
  const actorLabel = entry.actor
    ? entry.actor_name || entry.actor_email || t("unknownActor")
    : t("system");
  return (
    <tbody className="border-b border-border last:border-b-0">
      <tr className="align-top">
        <td className="whitespace-nowrap px-3 py-2 text-muted">
          {new Date(entry.at).toLocaleString(locale)}
        </td>
        <td className="px-3 py-2">
          <span className="font-medium" data-testid="audit-actor">
            {actorLabel}
          </span>
          {entry.actor_name && entry.actor_email ? (
            <span className="block text-xs text-muted">{entry.actor_email}</span>
          ) : null}
          <span className="block text-xs text-muted">
            {(entry.actor_roles ?? []).join(", ") || t("noRoles")}
          </span>
        </td>
        <td className="px-3 py-2 font-mono text-xs">{entry.action}</td>
        <td className="px-3 py-2">
          <span className="block">{entry.entity_type}</span>
          <span className="block text-xs text-muted" data-testid="audit-entity">
            {entry.entity_label ??
              (resourceId
                ? resourceId === entry.entity_id
                  ? t("shortId", { id: resourceId.slice(0, 8) })
                  : resourceId
                : "—")}
          </span>
        </td>
        <td className="px-3 py-2">
          <span data-testid="audit-outcome">
            {entry.outcome === "denied"
              ? t("outcomeDenied")
              : entry.outcome === "failed"
                ? t("outcomeFailed")
                : t("outcomeSuccess")}
          </span>
        </td>
      </tr>
      <tr>
        <td colSpan={5} className="px-3 pb-3">
          {entry.reason ? <p className="text-sm">{t("reason", { reason: entry.reason })}</p> : null}
          <details className="mt-1">
            <summary className="min-h-11 cursor-pointer py-2 text-sm font-medium text-primary">
              {t("changes", { count: changes.length })}
            </summary>
            {changes.length === 0 ? (
              <p className="text-sm text-muted">{t("noChanges")}</p>
            ) : (
              <table className="mt-1 w-full text-left text-xs" data-testid="audit-diff">
                <thead className="text-muted">
                  <tr>
                    <th scope="col" className="py-1 pr-3 font-medium">
                      {t("diffField")}
                    </th>
                    <th scope="col" className="py-1 pr-3 font-medium">
                      {t("diffBefore")}
                    </th>
                    <th scope="col" className="py-1 font-medium">
                      {t("diffAfter")}
                    </th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-border">
                  {changes.map((row) => (
                    <tr key={row.key}>
                      <td className="py-1 pr-3 font-mono">{row.key}</td>
                      <td className="break-all py-1 pr-3 text-danger">
                        {formatDiffValue(row.before) || "—"}
                      </td>
                      <td className="break-all py-1 text-success">
                        {formatDiffValue(row.after) || "—"}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
            <details className="mt-2">
              <summary className="min-h-11 cursor-pointer py-2 text-xs text-muted">
                {t("raw")}
              </summary>
              <pre className="overflow-x-auto whitespace-pre-wrap break-all text-xs">
                {JSON.stringify({ before: entry.before, after: entry.after }, null, 2)}
              </pre>
            </details>
            {entry.request_id ? (
              <p className="font-mono text-xs text-muted">
                {t("requestId", { id: entry.request_id })}
              </p>
            ) : null}
            {entry.entity_id || entry.actor ? (
              <p className="mt-1 flex flex-wrap gap-2">
                {entry.actor ? <CopyButton value={entry.actor} label={t("copyActorId")} /> : null}
                {entry.entity_id ? (
                  <CopyButton value={entry.entity_id} label={t("copyResourceId")} />
                ) : null}
              </p>
            ) : null}
          </details>
        </td>
      </tr>
    </tbody>
  );
}
