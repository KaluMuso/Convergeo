"use client";

import { EmptyState } from "@vergeo/ui/src/empty-state";
import { Skeleton } from "@vergeo/ui/src/skeleton";
import { useTranslations } from "next-intl";
import { useCallback, useEffect, useRef, useState } from "react";

import { rolesApi, useAdminPermissions } from "../../../lib/roles-api";
import { ConfirmModal } from "../_components/ConfirmModal";
import { CopyButton } from "../_components/CopyButton";

export type AdminAccount = {
  user_id: string;
  display_name: string | null;
  email: string | null;
  roles: string[];
};

type AccountsPage = {
  accounts: AdminAccount[];
  total?: number;
  next_offset?: number | null;
};

export const ACCOUNTS_PAGE_SIZE = 25;
const SEARCH_DEBOUNCE_MS = 300;

export function accountsQuery(search: string, offset: number): string {
  const params = new URLSearchParams({ limit: String(ACCOUNTS_PAGE_SIZE) });
  const term = search.trim();
  if (term) params.set("q", term);
  if (offset > 0) params.set("offset", String(offset));
  return params.toString();
}

export function AccountsBoard({ locale }: { locale: string }) {
  const t = useTranslations("admin.accountsUi");
  const tEmpty = useTranslations("admin.boards.states.accounts");
  const grants = useAdminPermissions();
  const canManage = grants?.can_manage_roles === true;
  const [accounts, setAccounts] = useState<AdminAccount[] | null>(null);
  const [total, setTotal] = useState<number | null>(null);
  const [nextOffset, setNextOffset] = useState<number | null>(null);
  const [search, setSearch] = useState("");
  const [appliedSearch, setAppliedSearch] = useState("");
  const [error, setError] = useState<"" | "loadFailed" | "mutationFailed" | "lastSuperadmin">("");
  const [loading, setLoading] = useState(false);
  const [busy, setBusy] = useState(false);
  const [target, setTarget] = useState<AdminAccount | null>(null);
  const [reason, setReason] = useState("");
  const inFlight = useRef(false);
  const generation = useRef(0);

  const load = useCallback(async (term: string, offset: number) => {
    const current = ++generation.current;
    setLoading(true);
    try {
      const result = await rolesApi.request<AccountsPage>(
        `/admin/accounts?${accountsQuery(term, offset)}`,
        { cache: "no-store" },
      );
      if (!Array.isArray(result?.accounts)) throw new Error("Invalid accounts response");
      if (current !== generation.current) return;
      setAccounts((previous) =>
        offset > 0 && previous ? [...previous, ...result.accounts] : result.accounts,
      );
      setTotal(typeof result.total === "number" ? result.total : null);
      setNextOffset(typeof result.next_offset === "number" ? result.next_offset : null);
      setError("");
    } catch {
      if (current !== generation.current) return;
      setAccounts(null);
      setError("loadFailed");
    } finally {
      if (current === generation.current) setLoading(false);
    }
  }, []);

  useEffect(() => {
    const timer = window.setTimeout(() => setAppliedSearch(search), SEARCH_DEBOUNCE_MS);
    return () => window.clearTimeout(timer);
  }, [search]);

  useEffect(() => {
    if (canManage) void load(appliedSearch, 0);
  }, [canManage, appliedSearch, load]);

  async function deactivate(): Promise<boolean> {
    const why = reason.trim();
    if (!target || inFlight.current || why.length < 3) return false;
    inFlight.current = true;
    setBusy(true);
    setError("");
    try {
      await rolesApi.request(`/admin/accounts/${encodeURIComponent(target.user_id)}/deactivate`, {
        method: "POST",
        body: JSON.stringify({ reason: why, confirmation: "DEACTIVATE" }),
      });
      setReason("");
      await load(appliedSearch, 0);
      return true;
    } catch (err) {
      const status = (err as { status?: number } | null)?.status;
      setError(status === 409 ? "lastSuperadmin" : "mutationFailed");
      return true;
    } finally {
      inFlight.current = false;
      setBusy(false);
    }
  }

  if (!canManage) return <p role="alert">{t("permissionDenied")}</p>;

  const label = (account: AdminAccount) => account.display_name ?? account.email ?? t("noName");

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
      <div className="flex flex-wrap items-end justify-between gap-3">
        <label className="block w-full max-w-md text-sm">
          {t("search")}
          <input
            type="search"
            value={search}
            placeholder={t("searchPlaceholder")}
            onChange={(event) => setSearch(event.target.value)}
            className="min-h-11 w-full rounded-md border border-border bg-surface p-2"
            data-testid="accounts-search"
          />
        </label>
        {accounts && total !== null ? (
          <p className="text-sm text-muted" data-testid="accounts-count">
            {t("showing", { shown: accounts.length, total })}
          </p>
        ) : null}
      </div>
      {error ? (
        <p role="alert" className="text-danger">
          {t(error)}
        </p>
      ) : null}
      {loading && accounts === null ? (
        <div className="space-y-3" data-testid="accounts-board-loading" aria-busy="true">
          <p className="sr-only">{t("loading")}</p>
          <Skeleton height="4rem" />
          <Skeleton height="4rem" />
          <Skeleton height="4rem" />
          <Skeleton height="4rem" />
        </div>
      ) : accounts === null ? (
        error ? (
          <button className="min-h-11 underline" onClick={() => void load(appliedSearch, 0)}>
            {t("retry")}
          </button>
        ) : null
      ) : accounts.length === 0 ? (
        appliedSearch.trim() ? (
          <EmptyState
            data-testid="accounts-board-no-match"
            title={t("noMatchTitle")}
            body={t("noMatchBody")}
          />
        ) : (
          <EmptyState
            data-testid="accounts-board-empty"
            title={tEmpty("emptyTitle")}
            body={tEmpty("emptyBody")}
          />
        )
      ) : (
        <div className="overflow-x-auto rounded-lg border border-border bg-surface">
          <table className="w-full text-left text-sm" data-testid="accounts-table">
            <thead className="border-b border-border text-xs text-muted">
              <tr>
                <th scope="col" className="px-3 py-2 font-medium">
                  {t("colName")}
                </th>
                <th scope="col" className="px-3 py-2 font-medium">
                  {t("colEmail")}
                </th>
                <th scope="col" className="px-3 py-2 font-medium">
                  {t("colRoles")}
                </th>
                <th scope="col" className="px-3 py-2">
                  <span className="sr-only">{t("colActions")}</span>
                </th>
              </tr>
            </thead>
            <tbody className="divide-y divide-border">
              {accounts.map((account) => (
                <tr key={account.user_id}>
                  <td className="px-3 py-2 font-medium">{account.display_name ?? t("noName")}</td>
                  <td className="px-3 py-2 text-muted">{account.email ?? t("noEmail")}</td>
                  <td className="px-3 py-2">{account.roles.join(", ")}</td>
                  <td className="px-3 py-2">
                    <div className="flex flex-wrap items-center justify-end gap-2">
                      <CopyButton
                        value={account.user_id}
                        label={t("copyId", { name: label(account) })}
                      />
                      {account.user_id === grants?.user_id ? (
                        <span className="text-xs text-muted">{t("selfNote")}</span>
                      ) : (
                        <button
                          type="button"
                          className="min-h-11 px-2 font-medium text-danger underline disabled:opacity-50"
                          disabled={busy}
                          onClick={() => {
                            setReason("");
                            setTarget(account);
                          }}
                        >
                          {t("deactivate")}
                        </button>
                      )}
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      {nextOffset !== null && accounts ? (
        <button
          type="button"
          className="min-h-11 rounded-md border border-border px-4 text-sm font-medium"
          disabled={loading}
          onClick={() => void load(appliedSearch, nextOffset)}
        >
          {loading ? t("loading") : t("more")}
        </button>
      ) : null}
      <ConfirmModal
        open={target !== null}
        data-testid="accounts-deactivate"
        destructive
        title={t("deactivateTitle")}
        summary={
          target
            ? t("confirmDeactivate", { name: label(target), roles: target.roles.join(", ") })
            : ""
        }
        confirmLabel={t("deactivate")}
        canConfirm={!busy && reason.trim().length >= 3}
        onConfirm={deactivate}
        onClose={() => setTarget(null)}
      >
        <label className="block text-sm">
          {t("reason")}
          <textarea
            value={reason}
            minLength={3}
            maxLength={500}
            rows={3}
            onChange={(event) => setReason(event.target.value)}
            className="mt-1 w-full rounded-md border border-border bg-surface p-2"
            data-testid="accounts-deactivate-reason"
          />
        </label>
      </ConfirmModal>
    </div>
  );
}
