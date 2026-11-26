"use client";

import { useTranslations } from "next-intl";
import { useCallback, useEffect, useRef, useState } from "react";

import {
  accountLabel,
  rolesApi,
  useAdminPermissions,
  useRefreshAdminPermissions,
  type AccountMatch,
  type AdminRole,
  type AdminRoleAssignment,
} from "../../../lib/roles-api";
import { AdminPageClient } from "../_components/admin-page-client";
import { adminPrimaryButtonClass } from "../_components/admin-primary-button";
import { ConfirmModal } from "../_components/ConfirmModal";

import { AccountPicker } from "./account-picker";

const PERMISSIONS = [
  "finance.read",
  "finance.operate",
  "events.manage",
  "products.manage",
  "services.read",
  "services.manage",
  "vendors.manage",
  "ads.manage",
  "analytics.read",
  "inventory.read",
  "support.manage",
  "logistics.manage",
  "audit.read",
] as const;

type RolesResponse = { roles: AdminRole[]; assignments: AdminRoleAssignment[] };

type PendingConfirm =
  | { kind: "delete"; role: AdminRole }
  | { kind: "revoke"; assignment: AdminRoleAssignment }
  | { kind: "superadmin"; account: AccountMatch };

const INPUT_CLASS = "min-h-11 w-full rounded-md border border-border bg-surface p-2";

export function RolesBoard() {
  const t = useTranslations("admin.rolesUi");
  const [data, setData] = useState<RolesResponse | null>(null);
  const grants = useAdminPermissions();
  const canManage = grants?.can_manage_roles === true;
  const refreshPermissions = useRefreshAdminPermissions();
  const [error, setError] = useState<"" | "loadFailed" | "mutationFailed" | "invalid">("");
  const [loading, setLoading] = useState(true);
  const active = useRef(false);
  const generation = useRef(0);
  const inFlight = useRef(false);
  const [busy, setBusy] = useState(false);
  const [key, setKey] = useState("");
  const [editingKey, setEditingKey] = useState("");
  const [name, setName] = useState("");
  const [selected, setSelected] = useState<string[]>([]);
  const [target, setTarget] = useState<AccountMatch | null>(null);
  const [assignedRole, setAssignedRole] = useState("");
  const [pending, setPending] = useState<PendingConfirm | null>(null);

  const reload = useCallback(async (current: number) => {
    setLoading(true);
    try {
      const result = await rolesApi.request<RolesResponse>("/admin/roles", {
        cache: "no-store",
      });
      if (!Array.isArray(result?.roles) || !Array.isArray(result?.assignments))
        throw new Error("Invalid roles response");
      if (active.current && current === generation.current) {
        setData(result);
        setError("");
      }
    } catch {
      if (active.current && current === generation.current) {
        setData(null);
        setError("loadFailed");
      }
    } finally {
      if (active.current && current === generation.current) setLoading(false);
    }
  }, []);

  useEffect(() => {
    active.current = canManage;
    const current = ++generation.current;
    setData(null);
    setError("");
    setBusy(false);
    setEditingKey("");
    setKey("");
    setName("");
    setSelected([]);
    setTarget(null);
    setAssignedRole("");
    setPending(null);
    inFlight.current = false;
    if (canManage) void reload(current);
    return () => {
      active.current = false;
      ++generation.current;
    };
    // A permission refresh can settle in one React batch without unmounting us.
    // Each fresh snapshot must still reload the definitions and assignments.
  }, [grants, canManage, reload]);

  async function mutate(path: string, method: string, body?: object) {
    // React state may not render between two clicks: acquire the guard first.
    if (!canManage || !active.current || !data || loading || inFlight.current) return false;
    inFlight.current = true;
    const current = generation.current;
    setBusy(true);
    setError("");
    try {
      await rolesApi.request(path, {
        method,
        body: body ? JSON.stringify(body) : undefined,
      });
      if (!active.current || current !== generation.current) return false;
      // Never construct grants from the submitted form. The shell clears the
      // snapshot, rechecks the API, and remounts the board only if still allowed.
      if (refreshPermissions) refreshPermissions();
      else await reload(current);
      return true;
    } catch {
      if (active.current && current === generation.current) setError("mutationFailed");
      return false;
    } finally {
      if (active.current && current === generation.current) {
        inFlight.current = false;
        setBusy(false);
      }
    }
  }

  function resetForm() {
    setEditingKey("");
    setKey("");
    setName("");
    setSelected([]);
  }

  function roleName(key: string) {
    if (key === "superadmin") return t("superadmin");
    if (key === "admin") return t("admin");
    return data?.roles.find((role) => role.key === key)?.name ?? key;
  }

  async function runConfirmed(action: PendingConfirm) {
    if (action.kind === "delete") {
      await mutate(`/admin/roles/${action.role.key}`, "DELETE");
    } else if (action.kind === "revoke") {
      await mutate(
        `/admin/roles/${encodeURIComponent(action.assignment.role)}/users/${encodeURIComponent(action.assignment.user_id)}`,
        "DELETE",
      );
    } else {
      await assignTo(action.account, "superadmin");
    }
    return true;
  }

  async function assignTo(account: AccountMatch, role: string) {
    const success = await mutate(
      `/admin/roles/${encodeURIComponent(role)}/users/${encodeURIComponent(account.user_id)}`,
      "PUT",
    );
    if (success && active.current) setTarget(null);
  }

  if (!canManage) return <p role="alert">{t("permissionDenied")}</p>;
  if (loading) return <p role="status">{t("loading")}</p>;
  if (!data)
    return (
      <div>
        <p role="alert">{t("loadFailed")}</p>
        <button className="min-h-11 underline" onClick={() => void reload(generation.current)}>
          {t("retry")}
        </button>
      </div>
    );

  return (
    <AdminPageClient title={t("title")} subtitle={t("subtitle")} className="space-y-6">
      <p className="text-sm text-text-2" data-testid="roles-deactivate-help">
        {t("deactivateHelp")}
      </p>
      <p className="text-sm text-text-2">{t("permissionsHelp")}</p>
      {error ? (
        <p role="alert" className="text-danger">
          {t(error)}
        </p>
      ) : null}
      <form
        className="space-y-3"
        aria-label={editingKey ? t("editHeading", { key: editingKey }) : t("createHeading")}
        onSubmit={(event) => {
          event.preventDefault();
          if (
            !/^[a-z][a-z0-9_]{2,39}$/.test(key) ||
            name.length < 3 ||
            name.length > 80 ||
            selected.length === 0
          ) {
            setError("invalid");
            return;
          }
          if (editingKey) {
            void mutate(`/admin/roles/${editingKey}`, "PATCH", {
              name,
              permissions: selected,
            });
          } else {
            void mutate("/admin/roles", "POST", {
              key: `rbac_${key}`,
              name,
              permissions: selected,
            }).then((success) => {
              if (success && active.current) resetForm();
            });
          }
        }}
      >
        <h2 className="font-semibold">
          {editingKey ? t("editHeading", { key: editingKey }) : t("createHeading")}
        </h2>
        <label className="block text-sm">
          {t("key")}
          <span className="flex items-center gap-2">
            {t("keyPrefix")}
            <input
              required
              pattern="[a-z][a-z0-9_]{2,39}"
              value={key}
              disabled={busy || !!editingKey}
              onChange={(event) => setKey(event.target.value)}
              className="min-h-11 rounded-md border border-border bg-surface p-2"
            />
          </span>
        </label>
        <label className="block text-sm">
          {t("name")}{" "}
          <input
            required
            disabled={busy}
            minLength={3}
            maxLength={80}
            value={name}
            onChange={(event) => setName(event.target.value)}
            className={INPUT_CLASS}
          />
        </label>
        <fieldset disabled={busy} className="grid gap-2 sm:grid-cols-2">
          <legend className="mb-2 text-sm font-semibold">{t("permissions")}</legend>
          {PERMISSIONS.map((permission) => (
            <label key={permission} className="flex items-center gap-2 text-sm">
              <input
                type="checkbox"
                checked={selected.includes(permission)}
                onChange={(event) =>
                  setSelected(
                    event.target.checked
                      ? [...selected, permission]
                      : selected.filter((value) => value !== permission),
                  )
                }
              />
              {permission}
            </label>
          ))}
        </fieldset>
        <button
          disabled={busy || selected.length === 0}
          className={`${adminPrimaryButtonClass} disabled:opacity-50`}
        >
          {editingKey ? t("save") : t("create")}
        </button>
        {editingKey ? (
          <button
            type="button"
            className="ml-3 min-h-11 underline"
            disabled={busy}
            onClick={resetForm}
          >
            {t("cancel")}
          </button>
        ) : null}
      </form>
      <section className="space-y-3">
        <h2 className="font-semibold">{t("current")}</h2>
        {data.roles.length === 0 ? <p>{t("emptyRoles")}</p> : null}
        {data.roles.map((role) => (
          <div key={role.key} className="rounded-lg border border-border bg-surface p-3 text-sm">
            <p className="font-semibold">
              {role.name} <code>{role.key}</code>
            </p>
            <p>{role.permissions.join(", ")}</p>
            <button
              disabled={busy}
              className="mr-4 min-h-11 underline"
              onClick={() => {
                setEditingKey(role.key);
                setKey(role.key.replace(/^rbac_/, ""));
                setName(role.name);
                setSelected(role.permissions);
              }}
            >
              {t("edit")}
            </button>
            <button
              disabled={busy}
              className="min-h-11 text-danger underline"
              onClick={() => setPending({ kind: "delete", role })}
            >
              {t("delete")}
            </button>
          </div>
        ))}
      </section>
      <section className="space-y-3">
        <h2 className="font-semibold">{t("assignHeading")}</h2>
        <form
          aria-label={t("assignHeading")}
          className="space-y-3"
          onSubmit={(event) => {
            event.preventDefault();
            if (
              !target ||
              !(
                assignedRole === "superadmin" ||
                data.roles.some((role) => role.key === assignedRole)
              )
            ) {
              setError("invalid");
              return;
            }
            if (assignedRole === "superadmin") {
              setPending({ kind: "superadmin", account: target });
              return;
            }
            void assignTo(target, assignedRole);
          }}
        >
          <AccountPicker value={target} onChange={setTarget} disabled={busy} />
          <label className="block text-sm">
            {t("role")}
            <select
              disabled={busy}
              value={assignedRole}
              onChange={(event) => setAssignedRole(event.target.value)}
              className={INPUT_CLASS}
            >
              <option value="">{t("choose")}</option>
              <option value="superadmin">{t("superadmin")}</option>
              {data?.roles.map((role) => (
                <option key={role.key} value={role.key}>
                  {role.name}
                </option>
              ))}
            </select>
          </label>
          <button
            disabled={busy || !target || !assignedRole}
            className={`${adminPrimaryButtonClass} disabled:opacity-50`}
          >
            {t("assign")}
          </button>
        </form>
        <h3 className="font-semibold">{t("assignments")}</h3>
        {data.assignments.length === 0 ? (
          <p>{t("emptyAssignments")}</p>
        ) : (
          <div className="overflow-x-auto rounded-lg border border-border bg-surface">
            <table className="w-full text-left text-sm" data-testid="roles-assignments">
              <thead className="border-b border-border text-xs text-muted">
                <tr>
                  <th scope="col" className="px-3 py-2 font-medium">
                    {t("colName")}
                  </th>
                  <th scope="col" className="px-3 py-2 font-medium">
                    {t("colEmail")}
                  </th>
                  <th scope="col" className="px-3 py-2 font-medium">
                    {t("role")}
                  </th>
                  <th scope="col" className="px-3 py-2">
                    <span className="sr-only">{t("colActions")}</span>
                  </th>
                </tr>
              </thead>
              <tbody className="divide-y divide-border">
                {data.assignments.map((assignment) => (
                  <tr key={`${assignment.user_id}:${assignment.role}`}>
                    <td className="px-3 py-2 font-medium">
                      {assignment.display_name || t("noName")}
                    </td>
                    <td className="px-3 py-2 text-muted">{assignment.email || t("noEmail")}</td>
                    <td className="px-3 py-2">{roleName(assignment.role)}</td>
                    <td className="px-3 py-2 text-right">
                      <button
                        disabled={busy}
                        className="min-h-11 text-danger underline"
                        onClick={() => setPending({ kind: "revoke", assignment })}
                      >
                        {t("revoke")}
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>
      <ConfirmModal
        open={pending !== null}
        data-testid="roles-confirm"
        destructive={pending?.kind !== "superadmin"}
        title={
          pending?.kind === "delete"
            ? t("deleteTitle")
            : pending?.kind === "revoke"
              ? t("revokeTitle")
              : t("superadminTitle")
        }
        summary={
          pending?.kind === "delete"
            ? t("confirmDelete", { name: pending.role.name })
            : pending?.kind === "revoke"
              ? t("confirmRevoke", {
                  role: roleName(pending.assignment.role),
                  name: accountLabel(pending.assignment),
                })
              : pending?.kind === "superadmin"
                ? t("confirmSuperadmin", { name: accountLabel(pending.account) })
                : ""
        }
        confirmLabel={
          pending?.kind === "delete"
            ? t("delete")
            : pending?.kind === "revoke"
              ? t("revoke")
              : t("assign")
        }
        canConfirm={!busy}
        onConfirm={() => (pending ? runConfirmed(pending) : Promise.resolve(true))}
        onClose={() => setPending(null)}
      />
    </AdminPageClient>
  );
}
