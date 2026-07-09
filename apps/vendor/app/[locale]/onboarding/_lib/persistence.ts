import {
  LOCAL_STORAGE_KEY,
  ONBOARDING_STEPS,
  type OnboardingDraft,
  type OnboardingStepKey,
} from "./types";

export const DEFAULT_DRAFT: OnboardingDraft = {
  step: 0,
  businessName: "",
  businessCategory: "",
  legalName: "",
  momoPhone: "",
  nrcPath: null,
  selfiePath: null,
};

export function stepKeyFromIndex(index: number): OnboardingStepKey {
  const clamped = Math.max(0, Math.min(index, ONBOARDING_STEPS.length - 1));
  return ONBOARDING_STEPS[clamped] ?? "business";
}

export function stepIndexFromKey(key: OnboardingStepKey): number {
  const index = ONBOARDING_STEPS.indexOf(key);
  return index >= 0 ? index : 0;
}

export function readLocalDraft(): OnboardingDraft | null {
  if (typeof window === "undefined") {
    return null;
  }

  try {
    const raw = window.localStorage.getItem(LOCAL_STORAGE_KEY);
    if (!raw) {
      return null;
    }
    const parsed = JSON.parse(raw) as Partial<OnboardingDraft>;
    return {
      ...DEFAULT_DRAFT,
      ...parsed,
      step: typeof parsed.step === "number" ? parsed.step : 0,
    };
  } catch {
    return null;
  }
}

export function writeLocalDraft(draft: OnboardingDraft): void {
  if (typeof window === "undefined") {
    return;
  }
  window.localStorage.setItem(LOCAL_STORAGE_KEY, JSON.stringify(draft));
}

export function clearLocalDraft(): void {
  if (typeof window === "undefined") {
    return;
  }
  window.localStorage.removeItem(LOCAL_STORAGE_KEY);
}

export function mergeDraftWithServer(
  local: OnboardingDraft | null,
  server: {
    business_name: string | null;
    business_category: string | null;
    momo_phone: string | null;
    nrc_path: string | null;
    selfie_path: string | null;
  },
): OnboardingDraft {
  const base = local ?? DEFAULT_DRAFT;
  return {
    step: base.step,
    businessName: base.businessName || server.business_name || "",
    businessCategory: base.businessCategory || server.business_category || "",
    // legal_name is collected + persisted client-side only (no server field).
    legalName: base.legalName || "",
    momoPhone: base.momoPhone || server.momo_phone || "",
    nrcPath: base.nrcPath ?? server.nrc_path,
    selfiePath: base.selfiePath ?? server.selfie_path,
  };
}

export function resolveResumeStep(
  draft: OnboardingDraft,
  options: { resubmitMode: boolean; rejectedDocs: ("nrc" | "selfie")[] | null },
): number {
  if (options.resubmitMode) {
    return stepIndexFromKey("kyc");
  }

  if (!draft.businessName.trim() || !draft.businessCategory.trim()) {
    return stepIndexFromKey("business");
  }

  if (!draft.nrcPath || !draft.selfiePath || !draft.momoPhone.trim() || !draft.legalName.trim()) {
    return stepIndexFromKey("kyc");
  }

  return Math.max(draft.step, stepIndexFromKey("review"));
}
