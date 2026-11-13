"use client";

import { useTranslations } from "next-intl";
import { useCallback, useEffect, useRef, useState } from "react";

import { rolesApi, useAdminPermissions } from "../../../lib/roles-api";

export type AdminAccount = {
  user_id: string;
  display_name: string | null;
  email: string | null;
  roles: string[];
};

export function AccountsBoard({ locale }: { locale: string }) {
  const t = useTranslations("admin.accountsUi");
  const grants = useAdminPermissions();
  const canManage = grants?.can_manage_roles === true;
  const [accounts, setAccounts] = useState<AdminAccount[] | null>(null);
  const [error, setError] = useState<"" | "loadFailed" | "mutationFailed" | "lastSuperadmin">("");
  const [busy, setBusy] = useState(false);
  const [reason, setReason] = useState<Record<string, string>>({});
  const inFlight = useRef(false);

  const reload = useCallback(async () => {
    try {
      const result = await rolesApi.request<{ accounts: AdminAccount[] }>("/admin/accounts", {
        cache: "no-store",
      });
      if (!Array.isArray(result?.accounts)) throw new Error("Invalid accounts response");
      setAccounts(result.accounts);
      setError("");
    } catch {
      setAccounts(null);
      setError("loadFailed");
    }
  }, []);

  useEffect(() => {
    if (canManage) void reload();
  }, [canManage, reload]);

  async function deactivate(account: AdminAccount) {
    const why = (reason[account.user_id] ?? "").trim();
    if (inFlight.current || why.length < 3) return;
    const label = account.display_name ?? account.email ?? account.user_id;
    if (!window.confirm(t("confirmDeactivate", { name: label, roles: account.roles.join(", ") })))
      return;
    inFlight.current = true;
    setBusy(true);
    setError("");
    try {
      await rolesApi.request(`/admin/accounts/${encodeURIComponent(account.user_id)}/deactivate`, {
        method: "POST",
        body: JSON.stringify({ reason: why, confirmation: "DEACTIVATE" }),
      });
      setReason((current) => ({ ...current, [account.user_id]: "" }));
      await reload();
    } catch (err) {
      const status = (err as { status?: number } | null)?.status;
      setError(status === 409 ? "lastSuperadmin" : "mutationFailed");
    } finally {
      inFlight.current = false;
      setBusy(false);
    }
  }

  if (!canManage) return <p role="alert">{t("permissionDenied")}</p>;

  return (
    <div className="space-y-6">
      <header className="space-y-1">
        <h1 className="font-serif text-xl">{t("title")}</h1>
        <p className="text-sm text-muted">{t("subtitle")}</p>
        <p className="text-sm text-muted">{t("deactivateHelp")}</p>
        <p className="text-sm">
          <a className="underline" href={`/${locale}/roles`}>
            {t("manageRolesLink")}
          </a>
        </p>
      </header>
      {error ? (
        <p role="alert" className="text-error">
          {t(error)}
        </p>
      ) : null}
      {accounts === null ? (
        error ? (
          <button className="min-h-11 underline" onClick={() => void reload()}>
            {t("retry")}
          </button>
        ) : (
          <p role="status">{t("loading")}</p>
        )
      ) : accounts.length === 0 ? (
        <p>{t("empty")}</p>
      ) : (
        <ul className="space-y-3">
          {accounts.map((account) => (
            <li key={account.user_id} className="space-y-2 rounded border p-3 text-sm">
              <p className="font-semibold">{account.display_name ?? t("noName")}</p>
              <p className="text-muted">{account.email ?? t("noEmail")}</p>
              <p className="font-mono text-xs text-muted">{account.user_id}</p>
              <p>{t("roles", { roles: account.roles.join(", ") })}</p>
              {account.user_id === grants?.user_id ? (
                <p className="text-xs text-muted">{t("selfNote")}</p>
              ) : (
                <div className="space-y-2">
                  <label className="block text-sm">
                    {t("reason")}
                    <input
                      value={reason[account.user_id] ?? ""}
                      disabled={busy}
                      minLength={3}
                      maxLength={500}
                      onChange={(event) =>
                        setReason((current) => ({
                          ...current,
                          [account.user_id]: event.target.value,
                        }))
                      }
                      className="min-h-11 w-full rounded border p-2"
                    />
                  </label>
                  <button
                    className="min-h-11 text-error underline disabled:opacity-50"
                    disabled={busy || (reason[account.user_id] ?? "").trim().length < 3}
                    onClick={() => void deactivate(account)}
                  >
                    {t("deactivate")}
                  </button>
                </div>
              )}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
