"use client";

import { useSession } from "@vergeo/auth/use-session";
import Link from "next/link";
import { useTranslations } from "next-intl";
import { useCallback, useEffect, useMemo, useState } from "react";

import { createServicesClient, type ServiceSummary } from "../_lib/services-client";
import { Badge, Spinner } from "../_lib/ui";

type ServicesManageListProps = {
  locale: string;
};

function statusBadgeVariant(
  status: ServiceSummary["status"],
): "new" | "free" | "sold_out" | "public" {
  if (status === "active") {
    return "free";
  }
  if (status === "draft") {
    return "new";
  }
  return "sold_out";
}

export function ServicesManageList({ locale }: ServicesManageListProps) {
  const ts = useTranslations("services");
  const { session, loading: sessionLoading } = useSession();
  const [items, setItems] = useState<ServiceSummary[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const getToken = useCallback(() => session?.access_token ?? null, [session?.access_token]);
  const servicesClient = useMemo(() => createServicesClient(getToken), [getToken]);

  useEffect(() => {
    if (sessionLoading) {
      return;
    }
    if (!session) {
      setLoading(false);
      return;
    }

    let cancelled = false;
    setLoading(true);
    servicesClient
      .listServices()
      .then((response) => {
        if (!cancelled) {
          setItems(response.items);
          setError(null);
        }
      })
      .catch(() => {
        if (!cancelled) {
          setError(ts("vendor.errors.loadFailed"));
        }
      })
      .finally(() => {
        if (!cancelled) {
          setLoading(false);
        }
      });

    return () => {
      cancelled = true;
    };
  }, [servicesClient, session, sessionLoading, ts]);

  if (sessionLoading || loading) {
    return (
      <div className="flex min-h-[40vh] items-center justify-center">
        <Spinner label={ts("vendor.list.loading")} />
      </div>
    );
  }

  if (!session) {
    return <p className="text-sm text-text-2">{ts("vendor.errors.authRequired")}</p>;
  }

  return (
    <div className="flex flex-col gap-4">
      <header className="space-y-2">
        <p className="text-xs uppercase tracking-wide text-text-2">{ts("vendor.eyebrow")}</p>
        <div className="flex items-start justify-between gap-3">
          <div>
            <h1 className="text-xl font-semibold text-text">{ts("vendor.list.title")}</h1>
            <p className="text-sm text-text-2">{ts("vendor.list.intro")}</p>
          </div>
          <Link
            href={`/${locale}/services/new`}
            className="inline-flex min-h-11 items-center rounded-md bg-primary px-3 text-sm font-medium text-surface"
          >
            {ts("vendor.list.createCta")}
          </Link>
        </div>
      </header>

      {error ? <p className="text-sm text-danger">{error}</p> : null}

      {items.length === 0 ? (
        <div className="rounded-lg border border-dashed border-border p-6 text-center">
          <p className="text-sm text-text-2">{ts("vendor.list.empty")}</p>
          <Link
            href={`/${locale}/services/new`}
            className="mt-3 inline-flex min-h-11 items-center text-sm font-medium text-primary"
          >
            {ts("vendor.list.createCta")}
          </Link>
        </div>
      ) : (
        <ul className="space-y-3">
          {items.map((service) => (
            <li key={service.id} className="rounded-lg border border-border p-3">
              <div className="flex items-start justify-between gap-2">
                <div className="min-w-0 space-y-1">
                  <p className="truncate font-medium text-text">{service.title}</p>
                  <p className="text-xs text-text-2">
                    {service.service_area ?? ts("vendor.list.noArea")}
                    {` · ${ts(`categories.${service.category}`)}`}
                  </p>
                </div>
                <Badge
                  variant={statusBadgeVariant(service.status)}
                  label={ts(`vendor.status.${service.status}`)}
                />
              </div>
              <Link
                href={`/${locale}/services/${service.id}/edit`}
                className="mt-3 inline-flex min-h-11 w-full items-center justify-center rounded-md border border-border px-4 text-sm font-medium"
              >
                {ts("vendor.list.editCta")}
              </Link>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
