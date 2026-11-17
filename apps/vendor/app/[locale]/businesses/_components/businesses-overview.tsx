"use client";

import { useSession } from "@vergeo/auth/use-session";
import { formatK } from "@vergeo/i18n";
import { Button } from "@vergeo/ui/src/button";
import { Input } from "@vergeo/ui/src/input";
import { Select } from "@vergeo/ui/src/select";
import Link from "next/link";
import { useTranslations } from "next-intl";
import { useCallback, useEffect, useMemo, useState } from "react";

import { readActingBranch, writeActingBranch } from "../../../../lib/acting-branch";
import { getVendorStorefrontUrl } from "../../../../lib/customer-app";
import { branchErrorKey } from "../_lib/branch-errors";
import {
  createBusinessesClient,
  isAllowedEvidence,
  type Business,
} from "../_lib/businesses-client";

import { BranchEvidence } from "./branch-evidence";

type Client = ReturnType<typeof createBusinessesClient>;

const STATUS_TONE: Record<string, string> = {
  approved: "bg-primary-tint text-success",
  pending_review: "bg-accent-tint text-accent-deep",
  info_requested: "bg-accent-tint text-accent-deep",
  draft: "bg-bg-2 text-text-2",
  rejected: "bg-bg-2 text-danger",
};

export function BusinessesOverview({ locale }: { locale: string }) {
  const t = useTranslations("vendor.branches");
  const { session } = useSession();
  const token = session?.access_token ?? null;
  const client = useMemo(() => createBusinessesClient(() => token), [token]);
  const [data, setData] = useState<{ enabled: boolean; businesses: Business[] } | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(() => {
    if (!token) return;
    client
      .list()
      .then((next) => {
        setData(next);
        setError(null);
      })
      .catch((err: unknown) => setError(branchErrorKey(err)));
  }, [client, token]);

  useEffect(() => {
    load();
  }, [load]);

  if (error) {
    return (
      <p role="alert" className="text-sm text-danger">
        {t(error.replace(/^branches\./, ""))}
      </p>
    );
  }
  if (!data) return <p className="text-sm text-text-2">{t("loading")}</p>;
  if (!data.enabled) return <p className="text-sm text-text-2">{t("disabled")}</p>;

  return (
    <div className="space-y-6">
      {data.businesses.map((business) => (
        <BusinessCard
          key={business.id}
          business={business}
          client={client}
          locale={locale}
          onChange={load}
        />
      ))}
    </div>
  );
}

function allowanceLine(business: Business, t: ReturnType<typeof useTranslations>): string {
  const a = business.allowance;
  const usage =
    a.limit === null
      ? t("allowance.usedUnlimited", { used: a.used })
      : t("allowance.used", { used: a.used, limit: a.limit });
  if (!a.can_add) {
    return `${usage} · ${t(a.blocked_reason === "unregistered" ? "allowance.blockedUnregistered" : "allowance.blockedPlan")}`;
  }
  if (a.next_billing_role === "addon" && a.next_price_ngwee !== null) {
    return `${usage} · ${t("allowance.nextAddon", { price: formatK(a.next_price_ngwee) })}`;
  }
  return `${usage} · ${t("allowance.nextIncluded")}`;
}

/** Shops customers can see (and that appear as "Other branches" to each other). */
export function liveShopCount(business: Business): number {
  return business.branches.filter((b) => b.branch_status === "approved" && b.status === "active")
    .length;
}

function ShopLink({ locale, slug, label }: { locale: string; slug: string; label: string }) {
  const href = getVendorStorefrontUrl(locale, slug);
  if (!href) return null;
  return (
    <a
      href={href}
      target="_blank"
      rel="noopener noreferrer"
      className="inline-flex min-h-9 items-center text-sm font-medium text-primary underline-offset-2 hover:underline"
    >
      {label}
    </a>
  );
}

function BusinessCard({
  business,
  client,
  locale,
  onChange,
}: {
  business: Business;
  client: Client;
  locale: string;
  onChange: () => void;
}) {
  const t = useTranslations("vendor.branches");
  const [acting, setActing] = useState<string>("primary");
  useEffect(() => setActing(readActingBranch(document.cookie)), []);
  const canAdd = business.allowance.can_add && business.owner_kyc_approved;

  return (
    <section className="space-y-3 rounded-lg border border-border bg-surface p-4 shadow-1">
      <header className="space-y-1">
        <h2 className="m-0 font-display text-h3 font-semibold text-display-ink">
          {business.legal_name}
        </h2>
        <p className="m-0 text-sm text-text-2">
          {t(`registration.${business.registration_type}`)}
          {business.pacra_number
            ? ` · ${t("registration.pacraLine", { number: business.pacra_number })}`
            : ""}
          {business.pacra_verified ? ` · ${t("registration.verified")}` : ""}
        </p>
        <p className="m-0 text-sm text-text-2">{allowanceLine(business, t)}</p>
        <p className="m-0 text-sm text-text-2">
          {business.staff_seats === null
            ? t("staff.unlimited", { used: business.staff_used })
            : t("staff.seats", { used: business.staff_used, seats: business.staff_seats })}
        </p>
        {!business.owner_kyc_approved ? (
          <p className="m-0 text-sm text-accent-deep">{t("ownerKycNeeded")}</p>
        ) : null}
      </header>

      <div className="space-y-1">
        <h3 className="m-0 text-base font-semibold text-text">
          {t("shops.heading", { count: business.branches.length })}
        </h3>
        <p className="m-0 text-sm text-text-2" data-testid="branches-customer-note">
          {liveShopCount(business) > 1 ? t("shops.otherBranchesLive") : t("shops.otherBranchesHint")}
        </p>
      </div>
      <ul className="m-0 list-none space-y-2 p-0" data-testid="business-shops">
        {business.branches.map((branch) => (
          <li key={branch.id} className="space-y-2 rounded border border-border p-3">
            <div className="flex flex-wrap items-center gap-2">
              <span className="font-medium text-text">{branch.display_name}</span>
              <span
                className={`rounded-pill px-2 py-0.5 text-micro font-semibold ${STATUS_TONE[branch.branch_status] ?? ""}`}
              >
                {t(`status.${branch.branch_status}`)}
              </span>
              {branch.is_primary ? (
                <span className="text-micro text-text-2">{t("primary")}</span>
              ) : null}
              {acting === branch.id || (acting === "primary" && branch.is_primary) ? (
                <span className="text-micro font-semibold text-primary">{t("acting")}</span>
              ) : (
                <button
                  type="button"
                  className="min-h-9 rounded px-2 text-micro font-medium text-primary hover:bg-bg-2 focus-visible:outline-none focus-visible:shadow-focusRing"
                  onClick={() => {
                    writeActingBranch(branch.is_primary ? null : branch.id);
                    window.location.reload();
                  }}
                >
                  {t("actions.workHere")}
                </button>
              )}
            </div>
            {branch.branch_status === "approved" && branch.status === "active" ? (
              <ShopLink locale={locale} slug={branch.slug} label={t("shops.viewShop")} />
            ) : (
              <p className="m-0 text-micro text-text-2">{t("shops.notListedYet")}</p>
            )}
            {branch.payout_on_hold ? (
              <p className="m-0 text-sm text-accent-deep">{t("payoutHold")}</p>
            ) : null}
            {branch.review_note ? (
              <p className="m-0 text-sm text-text-2">
                {t("reviewNote", { note: branch.review_note })}
              </p>
            ) : null}
            {!branch.is_primary &&
            (branch.branch_status === "draft" || branch.branch_status === "info_requested") ? (
              <BranchEvidence
                client={client}
                businessId={business.id}
                branch={branch}
                onSubmitted={onChange}
              />
            ) : null}
          </li>
        ))}
      </ul>

      <div className="flex flex-wrap gap-2">
        {canAdd ? (
          <Link
            href={`/${locale}/businesses/${business.id}/branches/new`}
            className="inline-flex min-h-11 items-center rounded bg-primary px-4 text-sm font-semibold text-[var(--primary-btn-fg)] no-underline hover:bg-[var(--primary-btn-hover)] focus-visible:outline-none focus-visible:shadow-focusRing"
          >
            {t("actions.addShop")}
          </Link>
        ) : null}
      </div>

      <RegistrationForm business={business} client={client} onSaved={onChange} />
    </section>
  );
}

function RegistrationForm({
  business,
  client,
  onSaved,
}: {
  business: Business;
  client: Client;
  onSaved: () => void;
}) {
  const t = useTranslations("vendor.branches");
  const [type, setType] = useState<"company" | "business_name" | "unregistered">(
    business.registration_type === "unspecified" ? "unregistered" : business.registration_type,
  );
  const [pacra, setPacra] = useState(business.pacra_number ?? "");
  const [file, setFile] = useState<File | null>(null);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<string | null>(null);

  const save = async () => {
    setBusy(true);
    setMessage(null);
    try {
      let certPath: string | undefined;
      if (type !== "unregistered" && file) {
        if (!isAllowedEvidence(file)) throw new Error("file");
        certPath = await client.uploadPacraCertificate(business.id, file);
      }
      await client.updateBusiness(business.id, {
        registration_type: type,
        ...(type !== "unregistered" && pacra ? { pacra_number: pacra } : {}),
        ...(certPath ? { pacra_cert_path: certPath } : {}),
      });
      setMessage("registration.saved");
      onSaved();
    } catch (err) {
      setMessage(
        err instanceof Error && err.message === "file"
          ? "errors.evidenceFile"
          : branchErrorKey(err).replace(/^branches\./, ""),
      );
    } finally {
      setBusy(false);
    }
  };

  return (
    <details className="rounded border border-border p-3">
      <summary className="cursor-pointer text-sm font-medium text-text">
        {t("registration.title")}
      </summary>
      <div className="mt-3 space-y-3">
        <p className="m-0 text-sm text-text-2">{t("registration.help")}</p>
        <label className="flex flex-col gap-1 text-sm">
          <span className="font-medium text-text">{t("registration.typeLabel")}</span>
          <Select
            size="sm"
            value={type}
            onChange={(event) => setType(event.target.value as typeof type)}
          >
            <option value="company">{t("registration.company")}</option>
            <option value="business_name">{t("registration.business_name")}</option>
            <option value="unregistered">{t("registration.unregistered")}</option>
          </Select>
        </label>
        {type !== "unregistered" ? (
          <>
            <label className="flex flex-col gap-1 text-sm">
              <span className="font-medium text-text">{t("registration.pacraNumber")}</span>
              <Input
                size="sm"
                value={pacra}
                maxLength={40}
                onChange={(event) => setPacra(event.target.value)}
              />
            </label>
            <label className="flex flex-col gap-1 text-sm">
              <span className="font-medium text-text">{t("registration.certificate")}</span>
              <input
                type="file"
                accept="image/jpeg,image/png,image/webp"
                onChange={(event) => setFile(event.target.files?.[0] ?? null)}
                className="text-sm text-text-2"
              />
            </label>
          </>
        ) : (
          <p className="m-0 text-sm text-text-2">{t("registration.unregisteredNote")}</p>
        )}
        {message ? (
          <p role="status" className="m-0 text-sm text-text-2">
            {t(message)}
          </p>
        ) : null}
        <Button
          size="sm"
          variant="secondary"
          onClick={() => void save()}
          disabled={busy}
          loading={busy}
          loadingLabel={t("actions.saving")}
        >
          {t("registration.save")}
        </Button>
      </div>
    </details>
  );
}
