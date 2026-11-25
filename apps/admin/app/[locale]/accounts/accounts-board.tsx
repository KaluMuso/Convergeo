"use client";

import { EmptyState } from "@vergeo/ui/src/empty-state";
import { Skeleton } from "@vergeo/ui/src/skeleton";
import { useTranslations } from "next-intl";
import { useCallback, useEffect, useRef, useState } from "react";

import { rolesApi, useAdminPermissions } from "../../../lib/roles-api";
import { AdminPageClient } from "../_components/admin-page-client";

export type AdminAccount = {
  user_id: string;
  display_name: string | null;
  email: string | null;
  roles: string[];
};

export function AccountsBoard({ locale }: { locale: string }) {
  const t = useTranslations("admin.accountsUi");
  const tEmpty = useTranslations("admin.boards.states.accounts");
  const grants = useAdminPermissions();
  const canManage = grants?.can_manage_roles === true;
  const [accounts, setAccounts] = useState<AdminAccount[] | null>(null);
  const [error, setError] = useState<"" | "loadFailed" | "mutationFailed" | "lastSuperadmin">("");
  const [loading, setLoading] = useState(false);
  const [busy, setBusy] = useState(false);
  const [reason, setReason] = useState<Record<string, string>>({});
  const inFlight = useRef(false);

  const reload = useCallback(async () => {
    setLoading(true);
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
    } finally {
      setLoading(false);
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
    <AdminPageClient title={t("title")} subtitle={t("subtitle")} className="space-y-6">
      <p className="text-sm text-text-2">{t("deactivateHelp")}</p>
      <p className="text-sm">
        <a
          className="min-h-11 inline-flex items-center font-medium text-primary underline-offset-2 hover:underline"
          href={`/${locale}/roles`}
        >
          {t("manageRolesLink")}
        </a>
      </p>
      {error ? (
        <p role="alert" className="text-error">
          {t(error)}
        </p>
      ) : null}
      {loading ? (
        <div className="space-y-3" data-testid="accounts-board-loading" aria-busy="true">
          <p className="sr-only">{t("loading")}</p>
          <Skeleton height="4rem" />
          <Skeleton height="4rem" />
          <Skeleton height="4rem" />
          <Skeleton height="4rem" />
        </div>
      ) : accounts === null ? (
        error ? (
          <button className="min-h-11 underline" onClick={() => void reload()}>
            {t("retry")}
          </button>
        ) : null
      ) : accounts.length === 0 ? (
        <EmptyState
          data-testid="accounts-board-empty"
          title={tEmpty("emptyTitle")}
          body={tEmpty("emptyBody")}
        />
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
    </AdminPageClient>
  );
}
