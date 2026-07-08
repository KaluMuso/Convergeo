"use client";

import { useSession } from "@vergeo/auth/use-session";
import { useRouter } from "next/navigation";
import { useTranslations } from "next-intl";
import { useEffect, useMemo, useState } from "react";

import { resolveStatusVariant, StatusScreen } from "../_components/status-screen";
import { createKycClient } from "../_lib/kyc-client";
import { Spinner } from "../_lib/ui";

import type { KycApplication } from "../_lib/types";

type StatusPageClientProps = {
  locale: string;
};

export function StatusPageClient({ locale }: StatusPageClientProps) {
  const t = useTranslations("vendor");
  const router = useRouter();
  const { session, loading: sessionLoading } = useSession();
  const [application, setApplication] = useState<KycApplication | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const kycClient = useMemo(
    () => createKycClient(() => session?.access_token ?? null),
    [session?.access_token],
  );

  useEffect(() => {
    if (sessionLoading) {
      return;
    }

    if (!session) {
      setLoading(false);
      return;
    }

    let cancelled = false;

    async function load() {
      try {
        const app = await kycClient.getApplication();
        if (cancelled) {
          return;
        }

        if (app.kyc_status === "draft") {
          router.replace(`/${locale}/onboarding`);
          return;
        }

        setApplication(app);
      } catch {
        if (!cancelled) {
          setError(t("onboarding.errors.loadFailed"));
        }
      } finally {
        if (!cancelled) {
          setLoading(false);
        }
      }
    }

    void load();
    return () => {
      cancelled = true;
    };
  }, [kycClient, locale, router, session, sessionLoading, t]);

  if (sessionLoading || loading) {
    return (
      <div className="flex min-h-dvh items-center justify-center">
        <Spinner label={t("onboarding.loading")} />
      </div>
    );
  }

  if (error || !application) {
    return (
      <main className="mx-auto flex min-h-dvh w-full max-w-[360px] flex-col gap-4 p-4">
        <p className="text-sm text-danger" role="alert">
          {error ?? t("onboarding.errors.loadFailed")}
        </p>
      </main>
    );
  }

  const variant = resolveStatusVariant(application.kyc_status);

  return (
    <StatusScreen
      variant={variant}
      rejectionReason={application.rejection_reason}
      dashboardHref={`/${locale}`}
      listingsHref={`/${locale}/listings/new`}
      resubmitHref={`/${locale}/onboarding`}
      labels={{
        heading: t("onboarding.status.heading"),
        pending: {
          title: t("onboarding.status.pending.title"),
          body: t("onboarding.status.pending.body"),
          cta: t("onboarding.status.pending.cta"),
        },
        approved: {
          title: t("onboarding.status.approved.title"),
          body: t("onboarding.status.approved.body"),
          cta: t("onboarding.status.approved.cta"),
          t2Link: t("onboarding.status.approved.t2Link"),
        },
        rejected: {
          title: t("onboarding.status.rejected.title"),
          body: t("onboarding.status.rejected.body"),
          reasonLabel: t("onboarding.status.rejected.reasonLabel"),
          resubmitCta: t("onboarding.status.rejected.resubmitCta"),
          gateNotice: t("onboarding.status.rejected.gateNotice"),
        },
        resubmit: {
          title: t("onboarding.status.resubmit.title"),
          body: t("onboarding.status.resubmit.body"),
          submit: t("onboarding.status.resubmit.submit"),
        },
        t2: {
          stubLabel: t("onboarding.t2.stubLabel"),
          stubBody: t("onboarding.t2.stubBody"),
        },
      }}
    />
  );
}
