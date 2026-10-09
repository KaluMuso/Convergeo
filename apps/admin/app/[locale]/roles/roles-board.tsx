"use client";

import { useTranslations } from "next-intl";
import { useCallback, useEffect, useState } from "react";

import { rolesApi, type AdminRole, type AdminRoleAssignment } from "../../../lib/roles-api";

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
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [key, setKey] = useState("");
  const [editingKey, setEditingKey] = useState("");
  const [name, setName] = useState("");
  const [selected, setSelected] = useState<string[]>([]);
  const [target, setTarget] = useState("");
  const [assignedRole, setAssignedRole] = useState("");

  const reload = useCallback(async () => {
    try {
      setData(await rolesApi.request<RolesResponse>("/admin/roles"));
      setError("");
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Unable to load roles");
    }
  }, []);
  useEffect(() => {
    void reload();
  }, [reload]);

  async function mutate(path: string, method: string, body?: object) {
    setBusy(true);
    setError("");
    try {
      await rolesApi.request(path, { method, body: body ? JSON.stringify(body) : undefined });
      await reload();
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Role change failed");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="space-y-6">
      <header>
        <h1 className="font-serif text-xl">{t("title")}</h1>
        <p className="text-sm text-muted">{t("subtitle")}</p>
      </header>
      {error ? (
        <p role="alert" className="text-error">
          {error}
        </p>
      ) : null}
      <form
        className="space-y-3"
        onSubmit={(event) => {
          event.preventDefault();
          if (editingKey) {
            void mutate(`/admin/roles/${editingKey}`, "PATCH", { name, permissions: selected });
          } else {
            void mutate("/admin/roles", "POST", {
              key: `rbac_${key}`,
              name,
              permissions: selected,
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
              disabled={!!editingKey}
              onChange={(event) => setKey(event.target.value)}
              className="min-h-11 rounded border p-2"
            />
          </span>
        </label>
        <label className="block text-sm">
          {t("name")}{" "}
          <input
            required
            minLength={3}
            maxLength={80}
            value={name}
            onChange={(event) => setName(event.target.value)}
            className="min-h-11 w-full rounded border p-2"
          />
        </label>
        <fieldset className="grid gap-2 sm:grid-cols-2">
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
            onClick={() => {
              setEditingKey("");
              setKey("");
              setName("");
              setSelected([]);
            }}
          >
            {t("cancel")}
          </button>
        ) : null}
      </form>
      <section className="space-y-3">
        <h2 className="font-semibold">{t("current")}</h2>
        {data?.roles.map((role) => (
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
        <label className="block text-sm">
          {t("accountUuid")}
          <input
            required
            value={target}
            onChange={(event) => setTarget(event.target.value)}
            className="min-h-11 w-full rounded border p-2"
          />
        </label>
        <label className="block text-sm">
          {t("role")}
          <select
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
          onClick={() => {
            if (
              assignedRole === "superadmin" &&
              !window.confirm(t("confirmSuperadmin", { userId: target }))
            )
              return;
            void mutate(`/admin/roles/${assignedRole}/users/${target}`, "PUT");
          }}
        >
          {t("assign")}
        </button>
        <h3 className="font-semibold">{t("assignments")}</h3>
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
                    t("confirmRevoke", { role: assignment.role, userId: assignment.user_id }),
                  )
                )
                  void mutate(
                    `/admin/roles/${assignment.role}/users/${assignment.user_id}`,
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
