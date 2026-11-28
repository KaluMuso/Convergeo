"use client";

import { Button } from "@vergeo/ui/src/button";
import Link from "next/link";
import { useTranslations } from "next-intl";
import { useCallback, useEffect, useState } from "react";

import { VendorPageSkeleton } from "../../../_components/page-skeleton";
import { SUPPLIER_TYPES, type MizStatus, type SupplierType } from "../../_lib/source";
import { sourceErrorKey, useSourceApi } from "../../_lib/use-source-api";

type OwnListing = {
  id: string;
  title: string;
  status: string;
  wholesale: boolean;
  made_in_zambia_status: MizStatus | null;
  made_in_zambia_reference: string | null;
  made_in_zambia_review_note: string | null;
};

/** Declare supplier types and CLAIM Made in Zambia on listings (an admin approves). */
export function SupplierProfile({ locale }: { locale: string }) {
  const t = useTranslations("vendor.source");
  const { client, ready } = useSourceApi();
  const [types, setTypes] = useState<SupplierType[] | null>(null);
  const [listings, setListings] = useState<OwnListing[] | null>(null);
  const [failed, setFailed] = useState(false);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [references, setReferences] = useState<Record<string, string>>({});
  const [pendingId, setPendingId] = useState<string | null>(null);

  const load = useCallback(() => {
    Promise.all([
      client.request<{ supplier_types: SupplierType[] }>("/vendor/sourcing/profile"),
      client.request<OwnListing[]>("/vendor/sourcing/listings"),
    ])
      .then(([profile, rows]) => {
        setTypes(profile.supplier_types);
        setListings(rows);
      })
      .catch(() => setFailed(true));
  }, [client]);

  useEffect(() => {
    if (ready) load();
  }, [ready, load]);

  async function saveTypes() {
    if (types === null) return;
    setBusy(true);
    setMessage(null);
    try {
      await client.request("/vendor/sourcing/profile", {
        method: "PUT",
        body: JSON.stringify({ supplier_types: types }),
      });
      setMessage(t("profile.saved"));
    } catch (error) {
      setMessage(t(sourceErrorKey(error)));
    } finally {
      setBusy(false);
    }
  }

  async function setClaim(listing: OwnListing, claim: boolean) {
    const reference = (references[listing.id] ?? "").trim();
    if (claim && reference && reference.length < 3) {
      setMessage(t("profile.miz.referenceTooShort"));
      return;
    }
    setMessage(null);
    setPendingId(listing.id);
    try {
      const updated = await client.request<OwnListing>(
        `/vendor/sourcing/listings/${listing.id}/made-in-zambia`,
        {
          method: "PUT",
          body: JSON.stringify(claim ? { claim, reference: reference || null } : { claim }),
        },
      );
      setListings((rows) =>
        (rows ?? []).map((row) => (row.id === listing.id ? { ...row, ...updated } : row)),
      );
      setMessage(t(claim ? "profile.miz.claimed" : "profile.miz.withdrawn"));
    } catch (error) {
      setMessage(t(sourceErrorKey(error)));
    } finally {
      setPendingId(null);
    }
  }

  if (failed)
    return (
      <p role="alert" className="text-sm text-text-2">
        {t("errors.load")}
      </p>
    );
  if (types === null || listings === null) {
    return <VendorPageSkeleton rows={3} label={t("loading")} />;
  }

  return (
    <div className="space-y-6">
      <Link href={`/${locale}/source`} className="text-sm text-primary underline">
        {t("profile.back")}
      </Link>
      {message ? (
        <p role="status" className="m-0 text-sm text-text">
          {message}
        </p>
      ) : null}
      <fieldset className="space-y-2 border-0 p-0">
        <legend className="mb-2 text-base font-semibold text-text">{t("profile.title")}</legend>
        {SUPPLIER_TYPES.map((type) => (
          <label key={type} className="flex min-h-11 items-center gap-3 text-body text-text">
            <input
              type="checkbox"
              checked={types.includes(type)}
              onChange={(event) =>
                setTypes(event.target.checked ? [...types, type] : types.filter((x) => x !== type))
              }
              className="size-5"
            />
            {t(`supplierTypes.${type}`)}
          </label>
        ))}
        <Button
          type="button"
          loading={busy}
          loadingLabel={t("profile.saving")}
          onClick={() => void saveTypes()}
        >
          {t("profile.save")}
        </Button>
      </fieldset>

      <section className="space-y-2">
        <h2 className="m-0 text-base font-semibold text-text">{t("profile.madeTitle")}</h2>
        <p className="m-0 text-sm text-text-2">{t("profile.madeIntro")}</p>
        {listings.length === 0 ? (
          <p className="text-sm text-text-2">{t("profile.noListings")}</p>
        ) : (
          <ul className="m-0 list-none space-y-3 p-0" data-testid="made-in-zambia-list">
            {listings.map((listing) => {
              const status = listing.made_in_zambia_status;
              const claimable = status === null || status === "rejected";
              return (
                <li
                  key={listing.id}
                  className="space-y-2 rounded-md border border-border p-3"
                  data-testid={`miz-${listing.id}`}
                >
                  <p className="m-0 text-body text-text">
                    {listing.title}
                    {listing.wholesale ? ` · ${t("profile.wholesaleTag")}` : ""}
                  </p>
                  <p className="m-0 text-sm text-text-2">
                    {t("profile.miz.statusLabel")}: {t(`profile.miz.status.${status ?? "none"}`)}
                    {listing.made_in_zambia_reference
                      ? ` · ${listing.made_in_zambia_reference}`
                      : ""}
                  </p>
                  {status === "rejected" && listing.made_in_zambia_review_note ? (
                    <p className="m-0 text-sm text-text-2">
                      {t("profile.miz.reviewNote", {
                        note: listing.made_in_zambia_review_note,
                      })}
                    </p>
                  ) : null}
                  {claimable ? (
                    <div className="space-y-2">
                      <label className="block text-sm text-text" htmlFor={`miz-ref-${listing.id}`}>
                        {t("profile.miz.referenceLabel")}
                      </label>
                      <input
                        id={`miz-ref-${listing.id}`}
                        value={references[listing.id] ?? ""}
                        maxLength={80}
                        placeholder={t("profile.miz.referencePlaceholder")}
                        onChange={(event) =>
                          setReferences((current) => ({
                            ...current,
                            [listing.id]: event.target.value,
                          }))
                        }
                        className="min-h-11 w-full rounded-md border border-border bg-surface px-3 text-body text-text"
                      />
                      <Button
                        type="button"
                        size="sm"
                        loading={pendingId === listing.id}
                        loadingLabel={t("profile.saving")}
                        onClick={() => void setClaim(listing, true)}
                      >
                        {t("profile.miz.send")}
                      </Button>
                    </div>
                  ) : null}
                  {status === "claimed" || status === "approved" ? (
                    <Button
                      type="button"
                      size="sm"
                      variant="secondary"
                      loading={pendingId === listing.id}
                      loadingLabel={t("profile.saving")}
                      onClick={() => void setClaim(listing, false)}
                    >
                      {t("profile.miz.withdraw")}
                    </Button>
                  ) : null}
                </li>
              );
            })}
          </ul>
        )}
      </section>
    </div>
  );
}
