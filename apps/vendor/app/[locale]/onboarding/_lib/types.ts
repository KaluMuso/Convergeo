export const ONBOARDING_STEPS = ["business", "kyc", "review"] as const;

export type OnboardingStepKey = (typeof ONBOARDING_STEPS)[number];

export type KycDocType = "nrc" | "selfie";

export type KycStatus =
  | "draft"
  | "submitted"
  | "under_review"
  | "approved"
  | "rejected"
  | "resubmit"
  | "suspended"
  | "revoked";

export type VendorStatus = "draft" | "pending_kyc" | "active" | "suspended";

export type KycApplication = {
  vendor_id: string;
  vendor_status: VendorStatus;
  /** Raw tier from API — may be orphaned without a record (MR-D02). Prefer helpers. */
  kyc_tier: number | null;
  kyc_status: KycStatus;
  tier: number | null;
  /** Present only when an auditable kyc_records row exists. */
  kyc_record_id: string | null;
  kyc_record_status: string | null;
  business_name: string | null;
  business_category: string | null;
  momo_phone: string | null;
  nrc_path: string | null;
  selfie_path: string | null;
  rejection_reason: string | null;
  rejected_docs: KycDocType[] | null;
  updated_at: string;
};

export type OnboardingDraft = {
  step: number;
  businessName: string;
  businessCategory: string;
  legalName: string;
  momoPhone: string;
  nrcPath: string | null;
  selfiePath: string | null;
};

export const BUSINESS_CATEGORIES = [
  "electronics",
  "home",
  "fashion_beauty",
  "services",
  "groceries",
  "other",
] as const;

export type BusinessCategory = (typeof BUSINESS_CATEGORIES)[number];

export const LOCAL_STORAGE_KEY = "vergeo5-vendor-onboarding";

// Private Supabase Storage bucket for KYC docs (created in config.toml by
// M12-P02b, which also adds the signed-upload endpoint used by storage.ts).
export const PRIVATE_KYC_BUCKET = "kyc-docs";
