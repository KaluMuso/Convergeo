"use client";

import { useSession } from "@vergeo/auth/use-session";
import { useRouter } from "next/navigation";
import { useTranslations } from "next-intl";
import { useCallback, useEffect, useMemo, useState } from "react";

import { VendorErrorState } from "../../_components/async-state";
import { VendorPage } from "../../_components/vendor-page";
import { ListSkeleton } from "../../_components/vendor-skeletons";
import { vendorErrorMessageKey } from "../../_lib/vendor-errors";
import { KycChecklistCard } from "../_components/kyc-checklist";
import { resolveHonestStatusVariant, StatusScreen } from "../_components/status-screen";
import { createKycClient } from "../_lib/kyc-client";

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
      <VendorPage width="form">
        <ListSkeleton label={t("onboarding.loading")} rows={5} />
      </VendorPage>
    );
  }

  if (!session) {
    return (
      <VendorPage width="form" className="min-h-dvh">
        <VendorErrorState
          title={t("onboarding.errors.authRequired")}
          retryLabel={tCommon("common.retry")}
        />
      </VendorPage>
    );
  }

  if (errorKey || !application) {
    return (
      <VendorPage width="form" className="min-h-dvh">
        <VendorErrorState
          title={t((errorKey ?? "onboarding.errors.loadFailed") as "onboarding.errors.loadFailed")}
          body={t("onboarding.errors.retryHint")}
          retryLabel={tCommon("common.retry")}
          onRetry={() => setReloadKey((value) => value + 1)}
        />
      </VendorPage>
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
      checklist={
        <KycChecklistCard application={application} locale={locale} showCta={false} embedded />
      }
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
