"use client";

import { useSession } from "@vergeo/auth/use-session";
import { ApiError } from "@vergeo/config";
import { useTranslations } from "next-intl";
import { useCallback, useEffect, useMemo, useState } from "react";

import { ngweeToZmwInput } from "../../listings/[id]/edit/_lib/money";
import {
  PACKAGE_LIMITS,
  PACKAGE_TIERS,
  createPackagesClient,
  draftFromPackage,
  emptyDraft,
  priceOrderWarnings,
  validateDraft,
  type PackageDraft,
  type PackageField,
  type PackageTier,
  type ServicePackage,
} from "../_lib/packages";
import { Button, FormField, Input } from "../_lib/ui";

type Props = { serviceId: string };

type TierState = {
  pkg: ServicePackage | null;
  draft: PackageDraft | null;
  errors: Partial<Record<PackageField, string>>;
  busy: boolean;
  message: string | null;
};

function apiErrorKey(error: unknown, fallback: string): string {
  if (error instanceof ApiError) {
    if (error.code === "prohibited_listing") return "errors.prohibited";
    if (error.code === "rate_limited" || error.status === 429) return "errors.rateLimited";
    if (error.code === "conflict") return "errors.conflict";
  }
  return fallback;
}

/**
 * Vendor editor for up to three packages. Validation mirrors the API so the
 * vendor sees which field is wrong; the API is still the gate. Removing a
 * package archives it (audited); saving it again brings it back.
 */
export function ServicePackagesEditor({ serviceId }: Props) {
  const t = useTranslations("services.vendor.packages");
  const tTier = useTranslations("services.packages.tier");
  const { session } = useSession();
  const getToken = useCallback(() => session?.access_token ?? null, [session?.access_token]);
  const client = useMemo(() => createPackagesClient(getToken), [getToken]);
  const [loadFailed, setLoadFailed] = useState(false);
  const [loaded, setLoaded] = useState(false);
  const [tiers, setTiers] = useState<Record<PackageTier, TierState>>(() => {
    const blank = (): TierState => ({
      pkg: null,
      draft: null,
      errors: {},
      busy: false,
      message: null,
    });
    return { basic: blank(), standard: blank(), premium: blank() };
  });

  const patch = useCallback((tier: PackageTier, next: Partial<TierState>) => {
    setTiers((prev) => ({ ...prev, [tier]: { ...prev[tier], ...next } }));
  }, []);

  const hasSession = Boolean(session?.access_token);
  useEffect(() => {
    if (!hasSession) return;
    let cancelled = false;
    client
      .list(serviceId)
      .then((response) => {
        if (cancelled) return;
        setTiers((prev) => {
          const next = { ...prev };
          for (const tier of PACKAGE_TIERS) {
            const pkg = response.items.find((item) => item.tier === tier) ?? null;
            next[tier] = {
              ...prev[tier],
              pkg,
              draft: pkg && pkg.status === "active" ? draftFromPackage(pkg, ngweeToZmwInput) : null,
            };
          }
          return next;
        });
        setLoaded(true);
      })
      .catch(() => {
        if (!cancelled) setLoadFailed(true);
      });
    return () => {
      cancelled = true;
    };
  }, [client, serviceId, hasSession]);

  const save = useCallback(
    async (tier: PackageTier) => {
      const draft = tiers[tier].draft;
      if (!draft) return;
      const verdict = validateDraft(draft);
      if (!verdict.ok) {
        patch(tier, { errors: verdict.errors, message: null });
        return;
      }
      patch(tier, { busy: true, errors: {}, message: null });
      try {
        const pkg = await client.upsert(serviceId, tier, verdict.payload);
        patch(tier, { pkg, busy: false, message: t("saved") });
      } catch (error) {
        patch(tier, { busy: false, message: t(apiErrorKey(error, "errors.saveFailed")) });
      }
    },
    [client, patch, serviceId, t, tiers],
  );

  const archive = useCallback(
    async (tier: PackageTier) => {
      if (!tiers[tier].pkg) {
        patch(tier, { draft: null, errors: {}, message: null });
        return;
      }
      patch(tier, { busy: true, message: null });
      try {
        const pkg = await client.archive(serviceId, tier);
        patch(tier, { pkg, draft: null, busy: false, errors: {} });
      } catch (error) {
        patch(tier, { busy: false, message: t(apiErrorKey(error, "errors.archiveFailed")) });
      }
    },
    [client, patch, serviceId, t, tiers],
  );

  const warnings = priceOrderWarnings(
    PACKAGE_TIERS.map((tier) => tiers[tier].pkg).filter((p): p is ServicePackage => Boolean(p)),
  );

  if (loadFailed) {
    return <p className="text-sm text-danger">{t("errors.loadFailed")}</p>;
  }
  if (!loaded) {
    return null;
  }

  return (
    <section
      className="mt-8 flex flex-col gap-4 border-t border-border pt-6"
      aria-labelledby="service-packages-editor-heading"
      data-testid="service-packages-editor"
    >
      <div className="space-y-1">
        <h2 id="service-packages-editor-heading" className="text-lg font-semibold text-text">
          {t("title")}
        </h2>
        <p className="text-sm text-text-2">{t("intro")}</p>
        <p className="text-xs text-text-3">{t("codNote")}</p>
        <p className="text-xs text-text-3">{t("guidance.fromPrice")}</p>
      </div>

      {warnings.map((w) => (
        <p
          key={`${w.higher}-${w.lower}`}
          role="status"
          className="text-sm text-warning"
          data-testid="packages-order-warning"
        >
          {t("guidance.order", { higher: tTier(w.higher), lower: tTier(w.lower) })}
        </p>
      ))}

      {PACKAGE_TIERS.map((tier) => {
        const state = tiers[tier];
        const draft = state.draft;
        const fieldError = (field: PackageField) =>
          state.errors[field] ? t(state.errors[field] as string) : undefined;
        const setDraft = (next: Partial<PackageDraft>) =>
          patch(tier, { draft: { ...(draft ?? emptyDraft()), ...next } });

        return (
          <div
            key={tier}
            className="flex flex-col gap-3 rounded-2 border border-border bg-surface p-4"
            data-testid={`package-panel-${tier}`}
          >
            <div className="flex flex-wrap items-center justify-between gap-2">
              <h3 className="font-semibold text-text">{tTier(tier)}</h3>
              {!draft ? (
                <span className="text-xs text-text-3">
                  {state.pkg?.status === "archived" ? t("archived") : t("notOffered")}
                </span>
              ) : null}
            </div>

            {!draft ? (
              <Button
                type="button"
                variant="secondary"
                loadingLabel={t("saving")}
                data-testid={`package-offer-${tier}`}
                onClick={() =>
                  patch(tier, {
                    draft: state.pkg ? draftFromPackage(state.pkg, ngweeToZmwInput) : emptyDraft(),
                    message: null,
                  })
                }
              >
                {t("offer")}
              </Button>
            ) : (
              <form
                className="flex flex-col gap-3"
                onSubmit={(event) => {
                  event.preventDefault();
                  void save(tier);
                }}
              >
                <FormField
                  label={t("nameLabel")}
                  helpText={t("nameHint")}
                  errorMessage={fieldError("name")}
                >
                  <Input
                    value={draft.name}
                    maxLength={PACKAGE_LIMITS.nameMax}
                    data-testid={`package-name-${tier}`}
                    onChange={(event) => setDraft({ name: event.target.value })}
                  />
                </FormField>
                <FormField label={t("descriptionLabel")} errorMessage={fieldError("description")}>
                  <Input
                    value={draft.description}
                    maxLength={PACKAGE_LIMITS.descriptionMax}
                    onChange={(event) => setDraft({ description: event.target.value })}
                  />
                </FormField>

                <fieldset className="flex flex-col gap-2">
                  <legend className="text-sm font-medium text-text">{t("priceModeLabel")}</legend>
                  <div className="flex flex-wrap gap-4 text-sm text-text">
                    {(["fixed", "quote"] as const).map((mode) => (
                      <label key={mode} className="flex min-h-11 items-center gap-2">
                        <input
                          type="radio"
                          name={`price-mode-${tier}`}
                          checked={draft.priceMode === mode}
                          data-testid={`package-price-mode-${mode}-${tier}`}
                          onChange={() => setDraft({ priceMode: mode })}
                        />
                        {mode === "fixed" ? t("priceModeFixed") : t("priceModeQuote")}
                      </label>
                    ))}
                  </div>
                </fieldset>
                {draft.priceMode === "fixed" ? (
                  <FormField label={t("priceLabel")} errorMessage={fieldError("price")}>
                    <Input
                      value={draft.price}
                      inputMode="decimal"
                      data-testid={`package-price-${tier}`}
                      onChange={(event) => setDraft({ price: event.target.value })}
                    />
                  </FormField>
                ) : null}

                <FormField label={t("deliveryLabel")} errorMessage={fieldError("delivery")}>
                  <Input
                    value={draft.deliveryDays}
                    inputMode="numeric"
                    data-testid={`package-delivery-${tier}`}
                    onChange={(event) => setDraft({ deliveryDays: event.target.value })}
                  />
                </FormField>

                <label className="flex min-h-11 items-center gap-2 text-sm text-text">
                  <input
                    type="checkbox"
                    checked={!draft.revisionsApplicable}
                    onChange={(event) => setDraft({ revisionsApplicable: !event.target.checked })}
                  />
                  {t("revisionsNA")}
                </label>
                {draft.revisionsApplicable ? (
                  <FormField label={t("revisionsLabel")} errorMessage={fieldError("revisions")}>
                    <Input
                      value={draft.revisions}
                      inputMode="numeric"
                      onChange={(event) => setDraft({ revisions: event.target.value })}
                    />
                  </FormField>
                ) : null}

                <FormField
                  label={t("includesLabel")}
                  helpText={t("includesHint")}
                  errorMessage={fieldError("includes")}
                >
                  <textarea
                    value={draft.includes}
                    rows={4}
                    className="min-h-11 w-full rounded-2 border border-border bg-bg px-3 py-2 text-sm text-text"
                    onChange={(event) => setDraft({ includes: event.target.value })}
                  />
                </FormField>

                {state.message ? (
                  <p
                    role="status"
                    className="text-sm text-text-2"
                    data-testid={`package-message-${tier}`}
                  >
                    {state.message}
                  </p>
                ) : null}

                <div className="flex flex-wrap gap-2">
                  <Button
                    type="submit"
                    variant="primary"
                    loading={state.busy}
                    loadingLabel={t("saving")}
                    disabled={state.busy}
                    data-testid={`package-save-${tier}`}
                  >
                    {t("save")}
                  </Button>
                  <Button
                    type="button"
                    variant="secondary"
                    loadingLabel={t("saving")}
                    disabled={state.busy}
                    data-testid={`package-archive-${tier}`}
                    onClick={() => void archive(tier)}
                  >
                    {t("archive")}
                  </Button>
                </div>
              </form>
            )}
          </div>
        );
      })}
    </section>
  );
}
