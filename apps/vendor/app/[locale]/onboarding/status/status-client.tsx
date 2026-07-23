"use client";

import { useSession } from "@vergeo/auth/use-session";
import { useRouter } from "next/navigation";
import { useTranslations } from "next-intl";
import { useCallback, useEffect, useMemo, useState } from "react";

import { VendorErrorState } from "../../_components/async-state";
import { vendorErrorMessageKey } from "../../_lib/vendor-errors";
import { resolveHonestStatusVariant, StatusScreen } from "../_components/status-screen";
import { createKycClient } from "../_lib/kyc-client";
import { Spinner } from "../_lib/ui";

import type { KycApplication } from "../_lib/types";

type StatusPageClientProps = {
  locale: string;
};

export function StatusPageClient({ locale }: StatusPageClientProps) {
  const t = useTranslations("vendor");
  const tCommon = useTranslations("common");
  const router = useRouter();
  const { session, loading: sessionLoading } = useSession();
  const [application, setApplication] = useState<KycApplication | null>(null);
  const [loading, setLoading] = useState(true);
  const [errorKey, setErrorKey] = useState<string | null>(null);
  const [reloadKey, setReloadKey] = useState(0);

  const kycClient = useMemo(
    () => createKycClient(() => session?.access_token ?? null),
    [session?.access_token],
  );

  const load = useCallback(async () => {
    if (!session) {
      setLoading(false);
      return;
    }
    setLoading(true);
    setErrorKey(null);
    try {
      // Resume (do not require vendor role) so invitees can check progress.
      const app = await kycClient.bootstrapApplication();
      if (app.kyc_status === "draft") {
        router.replace(`/${locale}/onboarding`);
        return;
      }
      setApplication(app);
    } catch (caught) {
      setApplication(null);
      setErrorKey(vendorErrorMessageKey(caught, "onboarding"));
    } finally {
      setLoading(false);
    }
  }, [kycClient, locale, router, session]);

  useEffect(() => {
    if (sessionLoading) {
      return;
    }
    if (!session) {
      setLoading(false);
      return;
    }
    void load();
  }, [load, session, sessionLoading, reloadKey]);

  if (sessionLoading || loading) {
    return (
      <div className="flex min-h-dvh items-center justify-center">
        <Spinner label={t("onboarding.loading")} />
      </div>
    );
  }

  if (!session) {
    return (
      <main className="mx-auto flex min-h-dvh w-full max-w-lg flex-col p-4">
        <VendorErrorState
          title={t("onboarding.errors.authRequired")}
          retryLabel={tCommon("common.retry")}
        />
      </main>
    );
  }

  if (errorKey || !application) {
    return (
      <main className="mx-auto flex min-h-dvh w-full max-w-lg flex-col p-4">
        <VendorErrorState
          title={t((errorKey ?? "onboarding.errors.loadFailed") as "onboarding.errors.loadFailed")}
          body={t("onboarding.errors.retryHint")}
          retryLabel={tCommon("common.retry")}
          onRetry={() => setReloadKey((value) => value + 1)}
        />
      </main>
    );
  }

  const variant = resolveHonestStatusVariant({
    kyc_status: application.kyc_status,
    kyc_record_id: application.kyc_record_id,
  });

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
