"use client";

import { useSession } from "@vergeo/auth/use-session";
import { useTranslations } from "next-intl";
import { useCallback, useEffect, useMemo, useState } from "react";

import { ServiceForm } from "../../../_components/service-form";
import { createServicesClient, type ServiceSummary } from "../../../_lib/services-client";
import { Spinner } from "../../../_lib/ui";

type ServiceEditViewProps = {
  locale: string;
  serviceId: string;
};

export function ServiceEditView({ locale, serviceId }: ServiceEditViewProps) {
  const ts = useTranslations("services");
  const { session, loading: sessionLoading } = useSession();
  const [service, setService] = useState<ServiceSummary | null>(null);
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
    servicesClient
      .listServices()
      .then((response) => {
        if (!cancelled) {
          const match = response.items.find((item) => item.id === serviceId) ?? null;
          setService(match);
          if (!match) {
            setError(ts("vendor.errors.loadFailed"));
          }
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
  }, [serviceId, servicesClient, session, sessionLoading, ts]);

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

  if (error || !service) {
    return <p className="text-sm text-danger">{error ?? ts("vendor.errors.loadFailed")}</p>;
  }

  return <ServiceForm locale={locale} mode="edit" serviceId={serviceId} initialService={service} />;
}
