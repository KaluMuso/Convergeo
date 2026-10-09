import { isValidZmMobile } from "./kyc-client";
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
  businessArchetype: "",
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

function draftKey(userId: string): string {
  return `${LOCAL_STORAGE_KEY}:${userId}`;
}

export function readLocalDraft(userId: string): OnboardingDraft | null {
  if (typeof window === "undefined" || !userId) {
    return null;
  }

  try {
    // The former unscoped key may belong to a different account on this device.
    window.localStorage.removeItem(LOCAL_STORAGE_KEY);
    const raw = window.localStorage.getItem(draftKey(userId));
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

export function writeLocalDraft(userId: string, draft: OnboardingDraft): void {
  if (typeof window === "undefined" || !userId) {
    return;
  }
  window.localStorage.setItem(draftKey(userId), JSON.stringify(draft));
}

export function clearLocalDraft(userId: string): void {
  if (typeof window === "undefined" || !userId) {
    return;
  }
  window.localStorage.removeItem(draftKey(userId));
}

export function mergeDraftWithServer(
  local: OnboardingDraft | null,
  server: {
    business_name: string | null;
    business_category: string | null;
    business_archetype: string | null;
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
    businessArchetype:
      base.businessArchetype || server.business_archetype || "",
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

  if (
    !draft.businessName.trim() ||
    !draft.businessCategory.trim() ||
    !draft.businessArchetype.trim()
  ) {
    return stepIndexFromKey("business");
  }

  if (
    !draft.nrcPath ||
    !draft.selfiePath ||
    !isValidZmMobile(draft.momoPhone) ||
    draft.legalName.trim().length < 2
  ) {
    return stepIndexFromKey("kyc");
  }

  return Math.max(draft.step, stepIndexFromKey("review"));
}
