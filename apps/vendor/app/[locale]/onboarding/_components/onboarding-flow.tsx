"use client";

import { useSession } from "@vergeo/auth/use-session";
import { useRouter } from "next/navigation";
import { useTranslations } from "next-intl";
import { useCallback, useEffect, useMemo, useState } from "react";

import { VendorErrorState } from "../../_components/async-state";
import { classifyVendorError, vendorErrorMessageKey } from "../../_lib/vendor-errors";
import {
  createKycClient,
  isResubmitStatus,
  isTerminalStatus,
  isValidZmMobile,
  normalizeZmPhone,
} from "../_lib/kyc-client";
import {
  clearLocalDraft,
  mergeDraftWithServer,
  readLocalDraft,
  resolveResumeStep,
  stepIndexFromKey,
  stepKeyFromIndex,
  writeLocalDraft,
} from "../_lib/persistence";
import { createStorageClient } from "../_lib/storage";
import { Spinner } from "../_lib/ui";

import { BusinessBasicsStep } from "./business-basics-step";
import { KycDocsStep } from "./kyc-docs-step";
import { ReviewStep } from "./review-step";
import { StepProgress } from "./step-progress";

import type { BusinessCategory, KycApplication, OnboardingDraft } from "../_lib/types";

type OnboardingFlowProps = {
  locale: string;
};

export function OnboardingFlow({ locale }: OnboardingFlowProps) {
  const t = useTranslations("vendor");
  const tCommon = useTranslations("common");
  const router = useRouter();
  const { session, loading: sessionLoading } = useSession();

  const [draft, setDraft] = useState<OnboardingDraft | null>(null);
  const [application, setApplication] = useState<KycApplication | null>(null);
  const [currentStep, setCurrentStep] = useState(0);
  const [loading, setLoading] = useState(true);
  const [submitting, setSubmitting] = useState(false);
  const [savingBasics, setSavingBasics] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [fatalErrorKey, setFatalErrorKey] = useState<string | null>(null);
  const [resubmitMode, setResubmitMode] = useState(false);
  const [reloadKey, setReloadKey] = useState(0);

  const getToken = useCallback(() => session?.access_token ?? null, [session?.access_token]);

  const kycClient = useMemo(() => createKycClient(getToken), [getToken]);
  const storageClient = useMemo(() => createStorageClient(getToken), [getToken]);

  const categoryLabels = useMemo(
    () => ({
      electronics: t("onboarding.business.categories.electronics"),
      home: t("onboarding.business.categories.home"),
      fashion_beauty: t("onboarding.business.categories.fashion_beauty"),
      services: t("onboarding.business.categories.services"),
      groceries: t("onboarding.business.categories.groceries"),
      other: t("onboarding.business.categories.other"),
    }),
    [t],
  );

  const stepLabels = useMemo(
    () => ({
      business: t("onboarding.steps.business"),
      kyc: t("onboarding.steps.kyc"),
      review: t("onboarding.steps.review"),
    }),
    [t],
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

    async function bootstrap() {
      setLoading(true);
      setFatalErrorKey(null);
      setError(null);
      try {
        // Idempotent server bootstrap — creates/resumes draft without vendor role.
        const app = await kycClient.bootstrapApplication();
        if (cancelled) {
          return;
        }

        if (isTerminalStatus(app.kyc_status)) {
          router.replace(`/${locale}/onboarding/status`);
          return;
        }

        const resubmit = isResubmitStatus(app.kyc_status);
        setResubmitMode(resubmit);
        setApplication(app);

        const local = readLocalDraft();
        const merged = mergeDraftWithServer(local, app);
        const step = resolveResumeStep(merged, {
          resubmitMode: resubmit,
          rejectedDocs: app.rejected_docs,
        });

        merged.step = step;
        setDraft(merged);
        setCurrentStep(step);
        writeLocalDraft(merged);
      } catch (caught) {
        if (cancelled) {
          return;
        }
        const kind = classifyVendorError(caught).kind;
        // Auth/permission failures must not fall back to a local-only draft —
        // that would look like a working onboarding without a server application.
        if (kind === "auth" || kind === "permission") {
          setFatalErrorKey(vendorErrorMessageKey(caught, "onboarding"));
          setDraft(null);
          return;
        }
        const local = readLocalDraft();
        if (local) {
          setDraft(local);
          setCurrentStep(local.step);
        } else {
          setDraft({
            step: 0,
            businessName: "",
            businessCategory: "",
            legalName: "",
            momoPhone: "",
            nrcPath: null,
            selfiePath: null,
          });
        }
        setError(t("onboarding.errors.loadFailed"));
      } finally {
        if (!cancelled) {
          setLoading(false);
        }
      }
    }

    void bootstrap();
    return () => {
      cancelled = true;
    };
  }, [kycClient, locale, reloadKey, router, session, sessionLoading, t]);

  const updateDraft = useCallback((patch: Partial<OnboardingDraft>) => {
    setDraft((prev) => {
      if (!prev) {
        return prev;
      }
      const next = { ...prev, ...patch };
      writeLocalDraft(next);
      return next;
    });
  }, []);

  const goToStep = useCallback(
    (step: number) => {
      setCurrentStep(step);
      updateDraft({ step });
    },
    [updateDraft],
  );

  const handleBusinessContinue = useCallback(async () => {
    if (!draft) {
      return;
    }
    setError(null);
    setSavingBasics(true);
    try {
      const app = await kycClient.saveDraft({
        business_name: draft.businessName.trim(),
        archetype: draft.businessCategory.trim() || null,
      });
      setApplication(app);
      goToStep(stepIndexFromKey("kyc"));
    } catch (caught) {
      const kind = classifyVendorError(caught).kind;
      if (kind === "auth" || kind === "permission") {
        setFatalErrorKey(vendorErrorMessageKey(caught, "onboarding"));
        return;
      }
      setError(t("onboarding.errors.saveFailed"));
    } finally {
      setSavingBasics(false);
    }
  }, [draft, goToStep, kycClient, t]);

  const handleKycContinue = useCallback(() => {
    if (!draft) {
      return;
    }
    const momo = normalizeZmPhone(draft.momoPhone);
    if (!isValidZmMobile(momo) || draft.legalName.trim().length < 2) {
      return;
    }
    setError(null);
    updateDraft({ momoPhone: momo });
    goToStep(stepIndexFromKey("review"));
  }, [draft, goToStep, updateDraft]);

  const handleUpload = useCallback(
    async (docType: "nrc" | "selfie", file: File) => {
      const signed = await storageClient.signKycUpload(docType, file.size);
      const path = await storageClient.uploadSigned(file, signed);
      if (docType === "nrc") {
        updateDraft({ nrcPath: path });
      } else {
        updateDraft({ selfiePath: path });
      }
      return path;
    },
    [storageClient, updateDraft],
  );

  const handleSubmit = useCallback(async () => {
    if (!draft) {
      return;
    }
    const docPaths = [draft.nrcPath, draft.selfiePath].filter((path): path is string =>
      Boolean(path),
    );
    if (docPaths.length === 0 || draft.legalName.trim().length < 2) {
      setError(t("onboarding.errors.submitFailed"));
      return;
    }
    setSubmitting(true);
    setError(null);
    try {
      const payload = {
        tier: 1,
        doc_storage_paths: docPaths,
        momo_phone: normalizeZmPhone(draft.momoPhone),
        momo_operator: null,
        legal_name: draft.legalName.trim(),
        archetype: draft.businessCategory.trim() || null,
        business_name: draft.businessName.trim() || null,
      };

      if (resubmitMode) {
        await kycClient.resubmit(payload);
      } else {
        await kycClient.submit(payload);
      }

      clearLocalDraft();
      router.push(`/${locale}/onboarding/status`);
    } catch {
      setError(t("onboarding.errors.submitFailed"));
    } finally {
      setSubmitting(false);
    }
  }, [draft, kycClient, locale, resubmitMode, router, t]);

  if (sessionLoading || loading) {
    return (
      <div className="flex min-h-[50dvh] items-center justify-center">
        <Spinner label={t("onboarding.loading")} />
      </div>
    );
  }

  if (!session) {
    return (
      <VendorErrorState
        title={t("onboarding.errors.authRequired")}
        retryLabel={tCommon("common.retry")}
      />
    );
  }

  if (fatalErrorKey) {
    return (
      <VendorErrorState
        title={t(fatalErrorKey as "onboarding.errors.permissionDenied")}
        body={t("onboarding.errors.retryHint")}
        retryLabel={tCommon("common.retry")}
        onRetry={() => setReloadKey((value) => value + 1)}
      />
    );
  }

  if (!draft) {
    return (
      <VendorErrorState
        title={t("onboarding.errors.loadFailed")}
        body={t("onboarding.errors.retryHint")}
        retryLabel={tCommon("common.retry")}
        onRetry={() => setReloadKey((value) => value + 1)}
      />
    );
  }

  const stepKey = stepKeyFromIndex(currentStep);
  const categoryLabel =
    categoryLabels[draft.businessCategory as BusinessCategory] ?? draft.businessCategory;

  return (
    <div className="flex flex-col gap-4">
      <div
        className="rounded border border-border bg-bg-2 px-3 py-2"
        data-testid="onboarding-invite-banner"
      >
        <p className="text-sm font-medium text-display-ink">{t("onboarding.invite.eyebrow")}</p>
        <p className="text-sm text-text-2">{t("onboarding.invite.body")}</p>
      </div>

      {!resubmitMode ? (
        <StepProgress
          currentStep={currentStep}
          labels={stepLabels}
          stepAnnouncement={(current, total) =>
            t("onboarding.stepAnnouncement", { current, total })
          }
          doneIndicator={t("onboarding.doneIndicator")}
        />
      ) : (
        <p className="text-sm font-medium text-primary">{t("onboarding.status.resubmit.title")}</p>
      )}

      {error ? (
        <div className="flex flex-col gap-2 rounded bg-danger/10 px-3 py-2" role="alert">
          <p className="text-sm text-danger">{error}</p>
          <button
            type="button"
            className="min-h-11 self-start text-sm font-medium text-primary underline"
            onClick={() => setReloadKey((value) => value + 1)}
          >
            {tCommon("common.retry")}
          </button>
        </div>
      ) : null}

      {stepKey === "business" && !resubmitMode ? (
        <BusinessBasicsStep
          businessName={draft.businessName}
          businessCategory={draft.businessCategory}
          onBusinessNameChange={(value) => updateDraft({ businessName: value })}
          onBusinessCategoryChange={(value) => updateDraft({ businessCategory: value })}
          onContinue={() => {
            void handleBusinessContinue();
          }}
          saving={savingBasics}
          labels={{
            heading: t("onboarding.business.heading"),
            intro: t("onboarding.business.intro"),
            nameLabel: t("onboarding.business.nameLabel"),
            namePlaceholder: t("onboarding.business.namePlaceholder"),
            categoryLabel: t("onboarding.business.categoryLabel"),
            categoryPlaceholder: t("onboarding.business.categoryPlaceholder"),
            categories: categoryLabels,
            continue: t("onboarding.business.continue"),
            saving: t("onboarding.business.saving"),
            required: t("onboarding.errors.required"),
          }}
        />
      ) : null}

      {stepKey === "kyc" || resubmitMode ? (
        <KycDocsStep
          momoPhone={draft.momoPhone}
          legalName={draft.legalName}
          nrcPath={draft.nrcPath}
          selfiePath={draft.selfiePath}
          rejectedDocs={application?.rejected_docs}
          onMomoPhoneChange={(value) => updateDraft({ momoPhone: value })}
          onLegalNameChange={(value) => updateDraft({ legalName: value })}
          onNrcUploaded={(path) => updateDraft({ nrcPath: path })}
          onSelfieUploaded={(path) => updateDraft({ selfiePath: path })}
          onContinue={() => {
            if (resubmitMode) {
              void handleSubmit();
            } else {
              handleKycContinue();
            }
          }}
          onUpload={handleUpload}
          labels={{
            heading: resubmitMode
              ? t("onboarding.status.resubmit.title")
              : t("onboarding.kyc.heading"),
            intro: resubmitMode ? t("onboarding.status.resubmit.body") : t("onboarding.kyc.intro"),
            nrcLabel: t("onboarding.kyc.nrcLabel"),
            nrcHelp: t("onboarding.kyc.nrcHelp"),
            selfieLabel: t("onboarding.kyc.selfieLabel"),
            selfieHelp: t("onboarding.kyc.selfieHelp"),
            legalNameLabel: t("onboarding.kyc.legalNameLabel"),
            legalNamePlaceholder: t("onboarding.kyc.legalNamePlaceholder"),
            legalNameHelp: t("onboarding.kyc.legalNameHelp"),
            momoLabel: t("onboarding.kyc.momoLabel"),
            momoPlaceholder: t("onboarding.kyc.momoPlaceholder"),
            momoHelp: t("onboarding.kyc.momoHelp"),
            continue: resubmitMode
              ? t("onboarding.status.resubmit.submit")
              : t("onboarding.kyc.continue"),
            uploading: t("onboarding.kyc.uploading"),
            capture: t("onboarding.kyc.capture"),
            retake: t("onboarding.kyc.retake"),
            usePhoto: t("onboarding.kyc.usePhoto"),
            uploadFailed: t("onboarding.kyc.uploadFailed"),
            uploaded: t("onboarding.kyc.uploaded"),
            nrcDone: t("onboarding.kyc.nrcDone"),
            selfieDone: t("onboarding.kyc.selfieDone"),
            required: t("onboarding.errors.required"),
            invalidPhone: t("onboarding.errors.invalidPhone"),
            quality: {
              heading: t("onboarding.quality.heading"),
              light: t("onboarding.quality.light"),
              steady: t("onboarding.quality.steady"),
              frame: t("onboarding.quality.frame"),
              face: t("onboarding.quality.face"),
            },
          }}
        />
      ) : null}

      {stepKey === "review" && !resubmitMode ? (
        <ReviewStep
          businessName={draft.businessName}
          businessCategory={draft.businessCategory}
          businessCategoryLabel={categoryLabel}
          momoPhone={draft.momoPhone}
          nrcUploaded={Boolean(draft.nrcPath)}
          selfieUploaded={Boolean(draft.selfiePath)}
          onEditBusiness={() => goToStep(stepIndexFromKey("business"))}
          onEditDocs={() => goToStep(stepIndexFromKey("kyc"))}
          onSubmit={() => void handleSubmit()}
          submitting={submitting}
          labels={{
            heading: t("onboarding.review.heading"),
            intro: t("onboarding.review.intro"),
            businessSection: t("onboarding.review.businessSection"),
            docsSection: t("onboarding.review.docsSection"),
            momoSection: t("onboarding.review.momoSection"),
            nrcUploaded: t("onboarding.review.nrcUploaded"),
            selfieUploaded: t("onboarding.review.selfieUploaded"),
            notUploaded: t("onboarding.review.notUploaded"),
            submit: t("onboarding.review.submit"),
            submitting: t("onboarding.review.submitting"),
            editBusiness: t("onboarding.review.editBusiness"),
            editDocs: t("onboarding.review.editDocs"),
            gateNotice: t("onboarding.review.gateNotice"),
          }}
        />
      ) : null}
    </div>
  );
}
