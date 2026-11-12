"use client";

import { useTranslations } from "next-intl";
import { useCallback, useEffect, useRef, useState } from "react";

import {
  rolesApi,
  useAdminPermissions,
  useRefreshAdminPermissions,
  type AdminRole,
  type AdminRoleAssignment,
} from "../../../lib/roles-api";

const PERMISSIONS = [
  "finance.read",
  "events.manage",
  "products.manage",
  "services.read",
  "vendors.manage",
  "ads.manage",
  "analytics.read",
  "inventory.read",
] as const;

type RolesResponse = { roles: AdminRole[]; assignments: AdminRoleAssignment[] };

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
  const [target, setTarget] = useState("");
  const [assignedRole, setAssignedRole] = useState("");

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
    setTarget("");
    setAssignedRole("");
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
    <div className="space-y-6">
      <header>
        <h1 className="font-serif text-xl">{t("title")}</h1>
        <p className="text-sm text-muted">{t("subtitle")}</p>
      </header>
      {error ? (
        <p role="alert" className="text-error">
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
              className="min-h-11 rounded border p-2"
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
            className="min-h-11 w-full rounded border p-2"
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
          className="min-h-11 rounded bg-primary px-4 text-white disabled:opacity-50"
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
          <div key={role.key} className="rounded border p-3 text-sm">
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
              className="min-h-11 text-error underline"
              onClick={() => {
                if (window.confirm(t("confirmDelete", { name: role.name })))
                  void mutate(`/admin/roles/${role.key}`, "DELETE");
              }}
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
              !/^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i.test(target) ||
              !(
                assignedRole === "superadmin" ||
                data.roles.some((role) => role.key === assignedRole)
              )
            ) {
              setError("invalid");
              return;
            }
            if (
              assignedRole === "superadmin" &&
              !window.confirm(t("confirmSuperadmin", { userId: target }))
            )
              return;
            void mutate(
              `/admin/roles/${encodeURIComponent(assignedRole)}/users/${encodeURIComponent(target)}`,
              "PUT",
            );
          }}
        >
          <label className="block text-sm">
            {t("accountUuid")}
            <input
              required
              disabled={busy}
              pattern="[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}"
              value={target}
              onChange={(event) => setTarget(event.target.value)}
              className="min-h-11 w-full rounded border p-2"
            />
          </label>
          <label className="block text-sm">
            {t("role")}
            <select
              disabled={busy}
              value={assignedRole}
              onChange={(event) => setAssignedRole(event.target.value)}
              className="min-h-11 w-full rounded border p-2"
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
            className="min-h-11 rounded bg-primary px-4 text-white disabled:opacity-50"
          >
            {t("assign")}
          </button>
        </form>
        <h3 className="font-semibold">{t("assignments")}</h3>
        {data.assignments.length === 0 ? <p>{t("emptyAssignments")}</p> : null}
        {data?.assignments.map((assignment) => (
          <div
            key={`${assignment.user_id}:${assignment.role}`}
            className="flex flex-wrap items-center justify-between gap-2 border-b py-2 text-sm"
          >
            <span>
              <code>{assignment.user_id}</code> · {assignment.role}
            </span>
            <button
              disabled={busy}
              className="min-h-11 text-error underline"
              onClick={() => {
                if (
                  window.confirm(
                    t("confirmRevoke", {
                      role: assignment.role,
                      userId: assignment.user_id,
                    }),
                  )
                )
                  void mutate(
                    `/admin/roles/${encodeURIComponent(assignment.role)}/users/${encodeURIComponent(assignment.user_id)}`,
                    "DELETE",
                  );
              }}
            >
              {t("revoke")}
            </button>
          </div>
        ))}
      </section>
    </div>
  );
}
