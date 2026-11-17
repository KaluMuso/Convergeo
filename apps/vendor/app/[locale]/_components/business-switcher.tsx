"use client";

import { useSession } from "@vergeo/auth/use-session";
import Link from "next/link";
import { useTranslations } from "next-intl";
import { useEffect, useMemo, useState } from "react";

import {
  PRIMARY_BRANCH,
  installActingBranchHeader,
  readActingBranch,
  writeActingBranch,
} from "../../../lib/acting-branch";
import { createBusinessesClient, type Business } from "../businesses/_lib/businesses-client";

installActingBranchHeader();

type BusinessSwitcherProps = { locale: string };

/**
 * "My businesses & shops" switcher (flag `multi_branch`). Renders nothing when the
 * flag is off or the owner has a single shop. Picking a shop stores it in the
 * acting-branch cookie and reloads, so every screen re-reads for that shop.
 */
export function BusinessSwitcher({ locale }: BusinessSwitcherProps) {
  const t = useTranslations("vendor.branches");
  const { session } = useSession();
  const token = session?.access_token ?? null;
  const client = useMemo(() => createBusinessesClient(() => token), [token]);
  const [businesses, setBusinesses] = useState<Business[] | null>(null);
  const [current, setCurrent] = useState<string>(PRIMARY_BRANCH);

  useEffect(() => {
    setCurrent(readActingBranch(document.cookie));
  }, []);

  useEffect(() => {
    if (!token) return;
    let cancelled = false;
    client
      .list()
      .then((data) => {
        if (!cancelled) setBusinesses(data.enabled ? data.businesses : []);
      })
      .catch(() => {
        if (!cancelled) setBusinesses([]);
      });
    return () => {
      cancelled = true;
    };
  }, [client, token]);

  const shops = (businesses ?? []).flatMap((business) => business.branches);
  if (!businesses || businesses.length === 0) return null;

  const primaryId = shops.find((shop) => shop.is_primary)?.id ?? "";
  const value = current === PRIMARY_BRANCH ? primaryId : current;
  const onChange = (next: string) => {
    if (next === value) return;
    writeActingBranch(next === primaryId ? null : next);
    window.location.reload();
  };

  return (
    <div className="flex min-w-0 items-center gap-1">
      {shops.length > 1 ? (
        <label className="flex min-w-0 items-center gap-1 text-sm">
          <span className="sr-only">{t("switcher.label")}</span>
          <select
            className="h-9 max-w-[11rem] truncate rounded border border-border bg-surface px-2 text-sm text-text sm:max-w-[16rem]"
            value={value}
            onChange={(event) => onChange(event.target.value)}
          >
            {businesses.map((business) => (
              <optgroup key={business.id} label={business.legal_name}>
                {business.branches.map((shop) => (
                  <option key={shop.id} value={shop.id}>
                    {shop.branch_status === "approved"
                      ? shop.display_name
                      : t("switcher.withStatus", {
                          name: shop.display_name,
                          status: t(`status.${shop.branch_status}`),
                        })}
                  </option>
                ))}
              </optgroup>
            ))}
          </select>
        </label>
      ) : null}
      <Link
        href={`/${locale}/businesses`}
        className="inline-flex min-h-9 items-center rounded px-2 text-sm font-medium text-primary no-underline hover:bg-bg-2 focus-visible:outline-none focus-visible:shadow-focusRing"
      >
        {t("switcher.manage")}
      </Link>
    </div>
  );
}
