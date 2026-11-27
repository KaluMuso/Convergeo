"use client";

import { Button } from "@vergeo/ui/src/button";
import Link from "next/link";
import { useTranslations } from "next-intl";
import { useCallback, useEffect, useState } from "react";

import { VendorPageSkeleton } from "../../../_components/page-skeleton";
import { SUPPLIER_TYPES, type SupplierType } from "../../_lib/source";
import { sourceErrorKey, useSourceApi } from "../../_lib/use-source-api";

type OwnListing = {
  id: string;
  title: string;
  status: string;
  wholesale: boolean;
  made_in_zambia: boolean;
};

/** Declare supplier types and mark listings Made in Zambia (self-declared). */
export function SupplierProfile({ locale }: { locale: string }) {
  const t = useTranslations("vendor.source");
  const { client, ready } = useSourceApi();
  const [types, setTypes] = useState<SupplierType[] | null>(null);
  const [listings, setListings] = useState<OwnListing[] | null>(null);
  const [failed, setFailed] = useState(false);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<string | null>(null);

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

  async function toggle(listing: OwnListing) {
    setMessage(null);
    const next = !listing.made_in_zambia;
    setListings((rows) =>
      (rows ?? []).map((row) => (row.id === listing.id ? { ...row, made_in_zambia: next } : row)),
    );
    try {
      await client.request(`/vendor/sourcing/listings/${listing.id}/made-in-zambia`, {
        method: "PUT",
        body: JSON.stringify({ made_in_zambia: next }),
      });
    } catch (error) {
      setListings((rows) =>
        (rows ?? []).map((row) =>
          row.id === listing.id ? { ...row, made_in_zambia: listing.made_in_zambia } : row,
        ),
      );
      setMessage(t(sourceErrorKey(error)));
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
          <ul className="m-0 list-none space-y-1 p-0" data-testid="made-in-zambia-list">
            {listings.map((listing) => (
              <li key={listing.id}>
                <label className="flex min-h-11 items-center gap-3 text-body text-text">
                  <input
                    type="checkbox"
                    checked={listing.made_in_zambia}
                    onChange={() => void toggle(listing)}
                    className="size-5"
                  />
                  <span>
                    {listing.title}
                    {listing.wholesale ? ` · ${t("profile.wholesaleTag")}` : ""}
                  </span>
                </label>
              </li>
            ))}
          </ul>
        )}
      </section>
    </div>
  );
}
