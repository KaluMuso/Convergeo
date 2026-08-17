"use client";

import { useSession } from "@vergeo/auth/use-session";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useTranslations } from "next-intl";
import { useCallback, useEffect, useMemo, useState } from "react";

import { VendorErrorState } from "../../../_components/async-state";
import { canUseWholesaleCapabilities, isAuditableApproved } from "../../../_lib/kyc-integrity";
import { vendorErrorMessageKey } from "../../../_lib/vendor-errors";
import { createKycClient } from "../../../onboarding/_lib/kyc-client";
import { createListingClient } from "../_lib/listing-client";
import { Spinner, Tabs } from "../_lib/ui";

import { AttachForm } from "./attach-form";
import { CanonicalSearch } from "./canonical-search";
import { NewCanonicalForm } from "./new-canonical-form";
import { QuickListForm } from "./quick-list-form";

import type { KycApplication } from "../../../onboarding/_lib/types";
import type { ListingCreateResponse, SuggestItem } from "../_lib/types";

type ListingCreateFlowProps = {
  locale: string;
};

type FlowTab = "attach" | "new_canonical" | "quick_list";

export function ListingCreateFlow({ locale }: ListingCreateFlowProps) {
  const t = useTranslations("vendor");
  const tCommon = useTranslations("common");
  const router = useRouter();
  const { session, loading: sessionLoading } = useSession();
  const [activeTab, setActiveTab] = useState<FlowTab>("attach");
  const [selectedProduct, setSelectedProduct] = useState<SuggestItem | null>(null);
  const [kycApp, setKycApp] = useState<KycApplication | null>(null);
  const [loadingTier, setLoadingTier] = useState(true);
  const [kycErrorKey, setKycErrorKey] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [successMessage, setSuccessMessage] = useState<string | null>(null);
  const [reloadKey, setReloadKey] = useState(0);

  const getToken = useCallback(() => session?.access_token ?? null, [session?.access_token]);
  const listingClient = useMemo(() => createListingClient(getToken), [getToken]);
  const kycClient = useMemo(() => createKycClient(getToken), [getToken]);

  const wholesaleEnabled = kycApp
    ? canUseWholesaleCapabilities({
        kyc_tier: kycApp.kyc_tier,
        kyc_status: kycApp.kyc_status,
        kyc_record_id: kycApp.kyc_record_id,
        kyc_record_status: kycApp.kyc_record_status,
      })
    : false;

  const kycApproved = kycApp
    ? isAuditableApproved({
        kyc_tier: kycApp.kyc_tier,
        kyc_status: kycApp.kyc_status,
        kyc_record_id: kycApp.kyc_record_id,
        kyc_record_status: kycApp.kyc_record_status,
      })
    : false;

  const fieldLabels = useMemo(
    () => ({
      priceLabel: t("listings.fields.priceLabel"),
      pricePlaceholder: t("listings.fields.pricePlaceholder"),
      priceHelp: t("listings.fields.priceHelp"),
      pricePerStepHelp: t("listings.fields.pricePerStepHelp"),
      priceInvalid: t("listings.fields.priceInvalid"),
      productClassLabel: t("listings.fields.productClassLabel"),
      classA: t("listings.fields.classA"),
      classB: t("listings.fields.classB"),
      classC: t("listings.fields.classC"),
      classD: t("listings.fields.classD"),
      classE: t("listings.fields.classE"),
      standaloneClassHint: t("listings.fields.standaloneClassHint"),
      saleUnitLabel: t("listings.fields.saleUnitLabel"),
      unitEach: t("listings.fields.unitEach"),
      unitMetre: t("listings.fields.unitMetre"),
      unitKg: t("listings.fields.unitKg"),
      unitLitre: t("listings.fields.unitLitre"),
      unitBag: t("listings.fields.unitBag"),
      unitSqm: t("listings.fields.unitSqm"),
      unitStepLabel: t("listings.fields.unitStepLabel"),
      unitStepHelp: t("listings.fields.unitStepHelp"),
      unitStepInvalid: t("listings.fields.unitStepInvalid"),
      minStepsLabel: t("listings.fields.minStepsLabel"),
      conditionLabel: t("listings.fields.conditionLabel"),
      conditionNew: t("listings.fields.conditionNew"),
      conditionRefurbished: t("listings.fields.conditionRefurbished"),
      conditionUsed: t("listings.fields.conditionUsed"),
      conditionDetailLabel: t("listings.fields.conditionDetailLabel"),
      conditionOpenBox: t("listings.fields.conditionOpenBox"),
      conditionUsedExcellent: t("listings.fields.conditionUsedExcellent"),
      conditionUsedGood: t("listings.fields.conditionUsedGood"),
      conditionUsedFair: t("listings.fields.conditionUsedFair"),
      conditionParts: t("listings.fields.conditionParts"),
      pricingModeLabel: t("listings.fields.pricingModeLabel"),
      pricingFixed: t("listings.fields.pricingFixed"),
      pricingMeasured: t("listings.fields.pricingMeasured"),
      pricingBundle: t("listings.fields.pricingBundle"),
      pricingTiered: t("listings.fields.pricingTiered"),
      pricingRange: t("listings.fields.pricingRange"),
      pricingFrom: t("listings.fields.pricingFrom"),
      pricingQuoteOnly: t("listings.fields.pricingQuoteOnly"),
      pricingQuoteHelp: t("listings.fields.pricingQuoteHelp"),
      defectNotesLabel: t("listings.fields.defectNotesLabel"),
      defectNotesPlaceholder: t("listings.fields.defectNotesPlaceholder"),
      defectNotesHelp: t("listings.fields.defectNotesHelp"),
      defectNotesInvalid: t("listings.fields.defectNotesInvalid"),
      fulfilmentLabel: t("listings.fields.fulfilmentLabel"),
      fulfilmentStocked: t("listings.fields.fulfilmentStocked"),
      fulfilmentMadeToOrder: t("listings.fields.fulfilmentMadeToOrder"),
      leadTimeLabel: t("listings.fields.leadTimeLabel"),
      leadTimeHelp: t("listings.fields.leadTimeHelp"),
      leadTimeInvalid: t("listings.fields.leadTimeInvalid"),
      capacityLabel: t("listings.fields.capacityLabel"),
      capacityHelp: t("listings.fields.capacityHelp"),
      capacityInvalid: t("listings.fields.capacityInvalid"),
      stockModeLabel: t("listings.fields.stockModeLabel"),
      stockTracked: t("listings.fields.stockTracked"),
      stockAlways: t("listings.fields.stockAlways"),
      stockQtyLabel: t("listings.fields.stockQtyLabel"),
      wholesaleLabel: t("listings.fields.wholesaleLabel"),
      wholesaleHelp: t("listings.fields.wholesaleHelp"),
      wholesaleMeasureUnavailable: t("listings.fields.wholesaleMeasureUnavailable"),
      moqLabel: t("listings.fields.moqLabel"),
      evidenceDraftNotice: t("listings.fields.evidenceDraftNotice"),
      saveDraft: t("listings.fields.saveDraft"),
      savingDraft: t("listings.fields.savingDraft"),
      required: t("listings.errors.required"),
    }),
    [t],
  );

  const commissionLabels = useMemo(
    () => ({
      heading: t("listings.commission.heading"),
      body: t("listings.commission.body"),
      rate: t("listings.commission.rate"),
    }),
    [t],
  );

  useEffect(() => {
    if (sessionLoading) {
      return;
    }
    if (!session) {
      setLoadingTier(false);
      return;
    }
    let cancelled = false;
    setLoadingTier(true);
    setKycErrorKey(null);
    void kycClient
      .getApplication()
      .then((app: KycApplication) => {
        if (!cancelled) {
          setKycApp(app);
        }
      })
      .catch((caught: unknown) => {
        if (!cancelled) {
          setKycApp(null);
          setKycErrorKey(vendorErrorMessageKey(caught, "listings"));
        }
      })
      .finally(() => {
        if (!cancelled) {
          setLoadingTier(false);
        }
      });
    return () => {
      cancelled = true;
    };
  }, [kycClient, reloadKey, session, sessionLoading]);

  const handleSuccess = (
    response: ListingCreateResponse,
    mode: FlowTab,
    requiresEvidence: boolean,
  ) => {
    if (requiresEvidence) {
      setSuccessMessage(t("listings.success.evidence"));
    } else if (mode === "new_canonical") {
      setSuccessMessage(t("listings.success.moderation"));
    } else {
      setSuccessMessage(t("listings.success.live"));
    }
    setError(null);
    window.setTimeout(() => {
      router.push(
        requiresEvidence
          ? `/${locale}/listings/${response.listing_id}/edit`
          : `/${locale}/listings`,
      );
    }, 1200);
  };

  if (sessionLoading || loadingTier) {
    return (
      <div className="flex min-h-[50dvh] items-center justify-center">
        <Spinner label={t("listings.loading")} />
      </div>
    );
  }

  if (!session) {
    router.replace(`/${locale}/login`);
    return null;
  }

  if (kycErrorKey) {
    return (
      <VendorErrorState
        title={t(kycErrorKey as "listings.errors.permissionDenied")}
        body={t("listings.errors.retryHint")}
        retryLabel={tCommon("common.retry")}
        onRetry={() => setReloadKey((value) => value + 1)}
      />
    );
  }

  const tabs = [
    {
      key: "attach",
      label: t("listings.tabs.attach"),
      panel: (
        <div className="flex flex-col gap-4">
          {!selectedProduct ? (
            <CanonicalSearch
              client={listingClient}
              selectedId={null}
              onSelect={setSelectedProduct}
              labels={{
                placeholder: t("listings.attach.searchPlaceholder"),
                searching: t("listings.attach.searching"),
                empty: t("listings.attach.empty"),
                hint: t("listings.attach.hint"),
              }}
            />
          ) : (
            <>
              <button
                type="button"
                className="min-h-11 self-start text-sm text-primary"
                onClick={() => setSelectedProduct(null)}
              >
                {t("listings.attach.changeProduct")}
              </button>
              <AttachForm
                client={listingClient}
                productId={selectedProduct.entity_id}
                wholesaleEnabled={wholesaleEnabled}
                onSuccess={(response, requiresEvidence) =>
                  handleSuccess(response, "attach", requiresEvidence)
                }
                onError={setError}
                labels={{
                  specHeading: t("listings.attach.specHeading"),
                  publish: t("listings.attach.publish"),
                  publishing: t("listings.attach.publishing"),
                  fields: fieldLabels,
                  commission: commissionLabels,
                  submitError: t("listings.errors.submitFailed"),
                  standaloneRequired: t("listings.errors.standalone_required"),
                }}
              />
            </>
          )}
        </div>
      ),
    },
    {
      key: "new_canonical",
      label: t("listings.tabs.newCanonical"),
      panel: (
        <NewCanonicalForm
          client={listingClient}
          wholesaleEnabled={wholesaleEnabled}
          onSuccess={(response, requiresEvidence) =>
            handleSuccess(response, "new_canonical", requiresEvidence)
          }
          onError={setError}
          labels={{
            heading: t("listings.newCanonical.heading"),
            intro: t("listings.newCanonical.intro"),
            nameLabel: t("listings.newCanonical.nameLabel"),
            namePlaceholder: t("listings.newCanonical.namePlaceholder"),
            brandLabel: t("listings.newCanonical.brandLabel"),
            brandPlaceholder: t("listings.newCanonical.brandPlaceholder"),
            categoryLabel: t("listings.newCanonical.categoryLabel"),
            categoryPlaceholder: t("listings.newCanonical.categoryPlaceholder"),
            submit: t("listings.newCanonical.submit"),
            submitting: t("listings.newCanonical.submitting"),
            moderationNotice: t("listings.newCanonical.moderationNotice"),
            fields: fieldLabels,
            commission: commissionLabels,
            submitError: t("listings.errors.submitFailed"),
            standaloneRequired: t("listings.errors.standalone_required"),
            required: t("listings.errors.required"),
          }}
        />
      ),
    },
    {
      key: "quick_list",
      label: t("listings.tabs.quickList"),
      panel: (
        <QuickListForm
          client={listingClient}
          wholesaleEnabled={wholesaleEnabled}
          onSuccess={(response, requiresEvidence) =>
            handleSuccess(response, "quick_list", requiresEvidence)
          }
          onError={setError}
          labels={{
            heading: t("listings.quickList.heading"),
            intro: t("listings.quickList.intro"),
            titleLabel: t("listings.quickList.titleLabel"),
            titlePlaceholder: t("listings.quickList.titlePlaceholder"),
            publish: t("listings.quickList.publish"),
            publishing: t("listings.quickList.publishing"),
            fields: fieldLabels,
            submitError: t("listings.errors.submitFailed"),
            standaloneRequired: t("listings.errors.standalone_required"),
            required: t("listings.errors.required"),
          }}
        />
      ),
    },
  ];

  return (
    <div className="flex flex-col gap-4">
      <header className="space-y-1">
        <h1 className="font-display text-h3 text-display-ink">{t("listings.title")}</h1>
        <p className="text-sm text-text-2">{t("listings.intro")}</p>
      </header>

      {!kycApproved ? (
        <div
          className="rounded-lg border border-warning/30 bg-warning/10 p-3 text-sm text-text"
          role="status"
        >
          <p className="font-medium">{t("listings.kycGate.title")}</p>
          <p className="mt-1">{t("listings.kycGate.body")}</p>
          <Link
            className="mt-2 inline-flex min-h-11 items-center font-medium text-primary underline"
            href={`/${locale}/onboarding/status`}
          >
            {t("listings.kycGate.cta")}
          </Link>
        </div>
      ) : null}

      {!wholesaleEnabled && kycApproved ? (
        <p className="text-xs text-text-2" role="note">
          {t("listings.kycGate.wholesaleLocked")}
        </p>
      ) : null}

      {error ? (
        <p
          role="alert"
          className="rounded-lg border border-danger/30 bg-danger/5 p-3 text-sm text-danger"
        >
          {error}
        </p>
      ) : null}
      {successMessage ? (
        <p
          role="status"
          className="rounded-lg border border-success/30 bg-success/5 p-3 text-sm text-success"
        >
          {successMessage}
        </p>
      ) : null}

      <Tabs
        ariaLabel={t("listings.tabs.ariaLabel")}
        items={tabs}
        value={activeTab}
        onValueChange={(key) => {
          setActiveTab(key as FlowTab);
          setError(null);
        }}
      />
    </div>
  );
}
