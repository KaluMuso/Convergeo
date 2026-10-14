"use client";

import { useSession } from "@vergeo/auth/use-session";
import { useRouter } from "next/navigation";
import { useTranslations } from "next-intl";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";

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
import { createStorageClient, isPrivateKycPath } from "../_lib/storage";
import { Spinner } from "../_lib/ui";

import { BusinessBasicsStep } from "./business-basics-step";
import { KycDocsStep } from "./kyc-docs-step";
import { ReviewStep } from "./review-step";
import { StepProgress } from "./step-progress";

import type {
  BusinessArchetype,
  BusinessCategory,
  KycApplication,
  OnboardingDraft,
} from "../_lib/types";

type OnboardingFlowProps = {
  locale: string;
};

export function OnboardingFlow({ locale }: OnboardingFlowProps) {
  const { session, loading } = useSession();
  const t = useTranslations("vendor");
  const tCommon = useTranslations("common");

  if (loading) {
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

  // Remount all draft/capture state at the account boundary, including A → B → A.
  return <AccountOnboardingFlow key={session.user.id} locale={locale} session={session} />;
}

function AccountOnboardingFlow({
  locale,
  session,
}: OnboardingFlowProps & { session: NonNullable<ReturnType<typeof useSession>["session"]> }) {
  const t = useTranslations("vendor");
  const tCommon = useTranslations("common");
  const router = useRouter();
  const userId = session.user.id;
  const activeSession = useRef({ active: false, generation: 0 });
  const [sessionGeneration, setSessionGeneration] = useState(0);
  const navigationGeneration = useRef(0);
  const pending = useRef({ basics: false, submit: false, upload: false });
  const isCurrentSession = useCallback(
    (generation: number) =>
      activeSession.current.active && activeSession.current.generation === generation,
    [],
  );
  const isCurrentOperation = useCallback(
    (generation: number, navigation: number) =>
      isCurrentSession(generation) && navigationGeneration.current === navigation,
    [isCurrentSession],
  );

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

  const archetypeLabels = useMemo(
    () => ({
      market_trader: t("onboarding.business.archetypes.market_trader"),
      registered_retailer: t("onboarding.business.archetypes.registered_retailer"),
      service_professional: t("onboarding.business.archetypes.service_professional"),
      manufacturer: t("onboarding.business.archetypes.manufacturer"),
      importer_wholesaler: t("onboarding.business.archetypes.importer_wholesaler"),
      event_organiser: t("onboarding.business.archetypes.event_organiser"),
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
    const generation = activeSession.current.generation + 1;
    activeSession.current = { active: true, generation };
    setSessionGeneration(generation);
    // A token refresh/retry cannot resend a submission that is still in flight.
    pending.current = { basics: false, submit: pending.current.submit, upload: false };

    async function bootstrap() {
      setLoading(true);
      setDraft(null);
      setApplication(null);
      setSavingBasics(false);
      setSubmitting(pending.current.submit);
      setCurrentStep(0);
      setResubmitMode(false);
      setFatalErrorKey(null);
      setError(null);
      try {
        // Idempotent server bootstrap — creates/resumes draft without vendor role.
        const app = await kycClient.bootstrapApplication();
        if (!isCurrentSession(generation)) {
          return;
        }

        if (isTerminalStatus(app.kyc_status)) {
          router.replace(`/${locale}/onboarding/status`);
          return;
        }

        const resubmit = isResubmitStatus(app.kyc_status);
        setResubmitMode(resubmit);
        setApplication(app);

        const local = readLocalDraft(userId);
        const merged = mergeDraftWithServer(local, app);
        const step = resolveResumeStep(merged, {
          resubmitMode: resubmit,
          rejectedDocs: app.rejected_docs,
        });

        merged.step = step;
        setDraft(merged);
        setCurrentStep(step);
        writeLocalDraft(userId, merged);
      } catch (caught) {
        if (!isCurrentSession(generation)) {
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
        const local = readLocalDraft(userId);
        if (local) {
          const step = resolveResumeStep(local, { resubmitMode: false, rejectedDocs: null });
          setDraft({ ...local, step });
          setCurrentStep(step);
        } else {
          setDraft({
            step: 0,
            businessName: "",
            businessCategory: "",
            businessArchetype: "",
            legalName: "",
            momoPhone: "",
            nrcPath: null,
            selfiePath: null,
          });
        }
        setError(t("onboarding.errors.loadFailed"));
      } finally {
        if (isCurrentSession(generation)) {
          setLoading(false);
        }
      }
    }

    void bootstrap();
    return () => {
      activeSession.current = { active: false, generation: generation + 1 };
    };
  }, [isCurrentSession, kycClient, locale, reloadKey, router, t, userId]);

  const updateDraft = useCallback(
    (patch: Partial<OnboardingDraft>) => {
      setDraft((prev) => {
        if (!prev || !isCurrentSession(sessionGeneration)) {
          return prev;
        }
        const next = { ...prev, ...patch };
        writeLocalDraft(userId, next);
        return next;
      });
    },
    [isCurrentSession, sessionGeneration, userId],
  );

  const goToStep = useCallback(
    (step: number) => {
      if (!isCurrentSession(sessionGeneration)) {
        return;
      }
      // Editing/back navigation cancels the UI effects of work from the old step.
      navigationGeneration.current += 1;
      setError(null);
      setCurrentStep(step);
      updateDraft({ step });
    },
    [isCurrentSession, sessionGeneration, updateDraft],
  );

  const handleBusinessContinue = useCallback(async () => {
    if (
      !draft ||
      !isCurrentSession(sessionGeneration) ||
      pending.current.basics ||
      pending.current.submit ||
      !draft.businessName.trim() ||
      !draft.businessCategory.trim() ||
      !draft.businessArchetype.trim()
    ) {
      return;
    }
    const navigation = navigationGeneration.current;
    pending.current.basics = true;
    setError(null);
    setSavingBasics(true);
    try {
      const app = await kycClient.saveDraft({
        business_name: draft.businessName.trim(),
        archetype: draft.businessCategory.trim() || null,
        business_archetype: draft.businessArchetype.trim() || null,
      });
      if (!isCurrentOperation(sessionGeneration, navigation)) {
        return;
      }
      setApplication(app);
      goToStep(stepIndexFromKey("kyc"));
    } catch (caught) {
      if (!isCurrentOperation(sessionGeneration, navigation)) {
        return;
      }
      const kind = classifyVendorError(caught).kind;
      if (kind === "auth" || kind === "permission") {
        setFatalErrorKey(vendorErrorMessageKey(caught, "onboarding"));
        return;
      }
      setError(t("onboarding.errors.saveFailed"));
    } finally {
      if (isCurrentSession(sessionGeneration)) {
        pending.current.basics = false;
        setSavingBasics(false);
      }
    }
  }, [draft, goToStep, isCurrentSession, isCurrentOperation, kycClient, sessionGeneration, t]);

  const handleKycContinue = useCallback(() => {
    if (!draft || !isCurrentSession(sessionGeneration) || pending.current.upload) {
      return;
    }
    const momo = normalizeZmPhone(draft.momoPhone);
    if (
      !isValidZmMobile(momo) ||
      draft.legalName.trim().length < 2 ||
      !isPrivateKycPath(draft.nrcPath ?? "") ||
      !isPrivateKycPath(draft.selfiePath ?? "")
    ) {
      return;
    }
    setError(null);
    updateDraft({ momoPhone: momo });
    goToStep(stepIndexFromKey("review"));
  }, [draft, goToStep, isCurrentSession, sessionGeneration, updateDraft]);

  const handleUpload = useCallback(
    async (docType: "nrc" | "selfie", file: File) => {
      const navigation = navigationGeneration.current;
      if (!isCurrentSession(sessionGeneration) || pending.current.upload) {
        throw new Error("Onboarding upload is no longer available");
      }
      pending.current.upload = true;
      try {
        const signed = await storageClient.signKycUpload(docType, file.size);
        if (!isCurrentOperation(sessionGeneration, navigation)) {
          throw new Error("Onboarding session changed");
        }
        const path = await storageClient.uploadSigned(file, signed);
        if (!isCurrentOperation(sessionGeneration, navigation)) {
          throw new Error("Onboarding session changed");
        }
        updateDraft(docType === "nrc" ? { nrcPath: path } : { selfiePath: path });
        return path;
      } finally {
        if (isCurrentSession(sessionGeneration)) {
          pending.current.upload = false;
        }
      }
    },
    [isCurrentSession, isCurrentOperation, sessionGeneration, storageClient, updateDraft],
  );

  const handleSubmit = useCallback(async () => {
    if (
      !draft ||
      !isCurrentSession(sessionGeneration) ||
      pending.current.submit ||
      pending.current.upload
    ) {
      return;
    }
    if (
      !isPrivateKycPath(draft.nrcPath ?? "") ||
      !isPrivateKycPath(draft.selfiePath ?? "") ||
      !isValidZmMobile(draft.momoPhone) ||
      draft.legalName.trim().length < 2
    ) {
      setError(t("onboarding.errors.submitFailed"));
      return;
    }
    const docPaths = [draft.nrcPath, draft.selfiePath].filter((path): path is string =>
      Boolean(path),
    );
    const navigation = navigationGeneration.current;
    pending.current.submit = true;
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
        business_archetype: draft.businessArchetype.trim() || null,
        business_name: draft.businessName.trim() || null,
      };

      if (resubmitMode) {
        await kycClient.resubmit(payload);
      } else {
        await kycClient.submit(payload);
      }

      if (!isCurrentOperation(sessionGeneration, navigation)) {
        return;
      }
      clearLocalDraft(userId);
      // Keep the submit lock until navigation/unmount, so repeats cannot resend.
      router.push(`/${locale}/onboarding/status`);
    } catch {
      if (isCurrentOperation(sessionGeneration, navigation)) {
        pending.current.submit = false;
        setSubmitting(false);
        setError(t("onboarding.errors.submitFailed"));
      }
    } finally {
      if (activeSession.current.active && !isCurrentOperation(sessionGeneration, navigation)) {
        pending.current.submit = false;
        setSubmitting(false);
      }
    }
  }, [
    draft,
    isCurrentSession,
    isCurrentOperation,
    kycClient,
    locale,
    resubmitMode,
    router,
    sessionGeneration,
    t,
    userId,
  ]);

  if (loading || !isCurrentSession(sessionGeneration)) {
    return (
      <div className="flex min-h-[50dvh] items-center justify-center">
        <Spinner label={t("onboarding.loading")} />
      </div>
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
  const archetypeLabel =
    archetypeLabels[draft.businessArchetype as BusinessArchetype] ?? draft.businessArchetype;

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
          businessArchetype={draft.businessArchetype}
          onBusinessNameChange={(value) => updateDraft({ businessName: value })}
          onBusinessCategoryChange={(value) => updateDraft({ businessCategory: value })}
          onBusinessArchetypeChange={(value) => updateDraft({ businessArchetype: value })}
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
            archetypeLabel: t("onboarding.business.archetypeLabel"),
            archetypePlaceholder: t("onboarding.business.archetypePlaceholder"),
            archetypes: archetypeLabels,
            continue: t("onboarding.business.continue"),
            saving: t("onboarding.business.saving"),
            required: t("onboarding.errors.required"),
          }}
        />
      ) : null}

      {stepKey === "kyc" || resubmitMode ? (
        <KycDocsStep
          key={`${userId}:${sessionGeneration}`}
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
          businessArchetype={draft.businessArchetype}
          businessArchetypeLabel={archetypeLabel}
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
            businessNameLabel: t("onboarding.review.businessNameLabel"),
            businessCategoryLabel: t("onboarding.review.businessCategoryLabel"),
            businessArchetypeLabel: t("onboarding.review.businessArchetypeLabel"),
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
