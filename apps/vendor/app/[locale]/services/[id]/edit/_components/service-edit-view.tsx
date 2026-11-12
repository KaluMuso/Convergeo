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

type ServiceLoad = {
  key: string | null;
  loading: boolean;
  service: ServiceSummary | null;
  error: string | null;
};

export function ServiceEditView({ locale, serviceId }: ServiceEditViewProps) {
  const ts = useTranslations("services");
  const { session, loading: sessionLoading } = useSession();
  const requestKey = session ? `${session.user.id}:${serviceId}` : null;
  const [load, setLoad] = useState<ServiceLoad>({
    key: null,
    loading: true,
    service: null,
    error: null,
  });

  const getToken = useCallback(() => session?.access_token ?? null, [session?.access_token]);
  const servicesClient = useMemo(() => createServicesClient(getToken), [getToken]);

  useEffect(() => {
    if (sessionLoading || !requestKey) {
      return;
    }

    let cancelled = false;
    setLoad({ key: requestKey, loading: true, service: null, error: null });
    servicesClient
      .listServices()
      .then((response) => {
        if (!cancelled) {
          const match = response.items.find((item) => item.id === serviceId) ?? null;
          setLoad({
            key: requestKey,
            loading: false,
            service: match,
            error: match ? null : ts("vendor.errors.loadFailed"),
          });
        }
      })
      .catch(() => {
        if (!cancelled) {
          setLoad({
            key: requestKey,
            loading: false,
            service: null,
            error: ts("vendor.errors.loadFailed"),
          });
        }
      });

    return () => {
      cancelled = true;
    };
  }, [serviceId, servicesClient, requestKey, sessionLoading, ts]);

  if (sessionLoading || (session && (load.key !== requestKey || load.loading))) {
    return (
      <div className="flex min-h-[40vh] items-center justify-center">
        <Spinner label={ts("vendor.list.loading")} />
      </div>
    );
  }

  if (!session) {
    return <p className="text-sm text-text-2">{ts("vendor.errors.authRequired")}</p>;
  }

  if (load.error || !load.service) {
    return <p className="text-sm text-danger">{load.error ?? ts("vendor.errors.loadFailed")}</p>;
  }

  return (
    <ServiceForm locale={locale} mode="edit" serviceId={serviceId} initialService={load.service} />
  );
}
