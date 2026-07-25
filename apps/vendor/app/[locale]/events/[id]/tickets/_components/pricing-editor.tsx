"use client";

import { ApiError } from "@vergeo/config";
import { formatK } from "@vergeo/i18n";
import { useTranslations } from "next-intl";
import { useCallback, useEffect, useState } from "react";

import { Button, FormField, Input, Spinner } from "../../../../listings/new/_lib/ui";
import { ngweeToZmwInput } from "../_lib/money";
import {
  isoToLocalDateTime,
  pricingErrorKey,
  resolveEarlyBird,
  resolveTiers,
  type TierDraft,
} from "../_lib/pricing";

import type { EarlyBirdInput, PriceTierRow, PricingConfig } from "../_lib/tickets-client";

type PricingClient = {
  getPricing(ticketTypeId: string): Promise<PricingConfig>;
  setEarlyBird(ticketTypeId: string, input: EarlyBirdInput): Promise<PricingConfig>;
  setPriceTiers(ticketTypeId: string, tiers: PriceTierRow[]): Promise<PricingConfig>;
};

type PricingEditorProps = {
  ticketTypeId: string;
  ticketsClient: PricingClient;
};

const EMPTY_TIER: TierDraft = { minQty: "", priceZmw: "" };

function tierDraftsFromConfig(config: PricingConfig): TierDraft[] {
  if (config.tiers.length === 0) {
    return [{ ...EMPTY_TIER }];
  }
  return config.tiers.map((tier) => ({
    minQty: String(tier.min_qty),
    priceZmw: ngweeToZmwInput(tier.price_ngwee),
  }));
}

export function PricingEditor({ ticketTypeId, ticketsClient }: PricingEditorProps) {
  const t = useTranslations("vendor");
  const [config, setConfig] = useState<PricingConfig | null>(null);
  const [ebPrice, setEbPrice] = useState("");
  const [ebUntil, setEbUntil] = useState("");
  const [tierRows, setTierRows] = useState<TierDraft[]>([{ ...EMPTY_TIER }]);
  const [loading, setLoading] = useState(true);
  const [savingEb, setSavingEb] = useState(false);
  const [savingTiers, setSavingTiers] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  const populate = useCallback((data: PricingConfig) => {
    setConfig(data);
    setEbPrice(
      data.early_bird_price_ngwee === null ? "" : ngweeToZmwInput(data.early_bird_price_ngwee),
    );
    setEbUntil(isoToLocalDateTime(data.early_bird_until));
    setTierRows(tierDraftsFromConfig(data));
  }, []);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      populate(await ticketsClient.getPricing(ticketTypeId));
    } catch {
      setError(t("tickets.pricing.errors.loadFailed"));
    } finally {
      setLoading(false);
    }
  }, [populate, t, ticketTypeId, ticketsClient]);

  useEffect(() => {
    void load();
  }, [load]);

  const apiErrorMessage = (err: unknown): string => {
    const key = err instanceof ApiError ? pricingErrorKey(err.code) : "errors.saveFailed";
    return t(`tickets.pricing.${key}`);
  };

  const handleSaveEarlyBird = async () => {
    if (!config) {
      return;
    }
    const resolution = resolveEarlyBird(
      { priceZmw: ebPrice, untilLocal: ebUntil },
      config.base_price_ngwee,
      new Date(),
    );
    if (!resolution.ok) {
      setError(t(`tickets.pricing.${resolution.errorKey}`));
      return;
    }
    setSavingEb(true);
    setError(null);
    setNotice(null);
    try {
      populate(await ticketsClient.setEarlyBird(ticketTypeId, resolution.input));
      setNotice(t("tickets.pricing.earlyBird.saved"));
    } catch (err) {
      setError(apiErrorMessage(err));
    } finally {
      setSavingEb(false);
    }
  };

  const handleSaveTiers = async () => {
    if (!config) {
      return;
    }
    const resolution = resolveTiers(tierRows, config.base_price_ngwee);
    if (!resolution.ok) {
      setError(t(`tickets.pricing.${resolution.errorKey}`));
      return;
    }
    setSavingTiers(true);
    setError(null);
    setNotice(null);
    try {
      populate(await ticketsClient.setPriceTiers(ticketTypeId, resolution.tiers));
      setNotice(t("tickets.pricing.tiers.saved"));
    } catch (err) {
      setError(apiErrorMessage(err));
    } finally {
      setSavingTiers(false);
    }
  };

  const updateTier = (index: number, patch: Partial<TierDraft>) => {
    setTierRows((current) => current.map((row, i) => (i === index ? { ...row, ...patch } : row)));
  };

  const addTier = () => setTierRows((current) => [...current, { ...EMPTY_TIER }]);

  const removeTier = (index: number) => {
    setTierRows((current) => {
      const next = current.filter((_, i) => i !== index);
      return next.length === 0 ? [{ ...EMPTY_TIER }] : next;
    });
  };

  if (loading) {
    return (
      <div className="flex items-center gap-2 py-2">
        <Spinner label={t("tickets.pricing.loading")} />
        <span className="sr-only">{t("tickets.pricing.loading")}</span>
      </div>
    );
  }

  return (
    <div className="mt-3 flex flex-col gap-4 rounded-md bg-bg-2/40 p-3">
      <div>
        <p className="text-sm font-medium">{t("tickets.pricing.heading")}</p>
        <p className="text-xs text-muted">
          {t("tickets.pricing.baseLabel", {
            price: config ? formatK(config.base_price_ngwee) : "",
          })}
        </p>
      </div>

      {error ? (
        <p className="rounded-md bg-danger/10 px-3 py-2 text-sm text-danger" role="alert">
          {error}
        </p>
      ) : null}
      {notice ? (
        <p className="rounded-md bg-primary/10 px-3 py-2 text-sm text-primary" role="status">
          {notice}
        </p>
      ) : null}

      {/* Early-bird */}
      <section className="flex flex-col gap-2">
        <p className="text-sm font-medium">{t("tickets.pricing.earlyBird.heading")}</p>
        <p className="text-xs text-muted">{t("tickets.pricing.earlyBird.help")}</p>
        <div className="flex flex-wrap items-end gap-3">
          <FormField label={t("tickets.pricing.earlyBird.priceLabel")}>
            <Input
              inputMode="decimal"
              value={ebPrice}
              onChange={(event) => setEbPrice(event.target.value)}
              placeholder={t("tickets.pricing.earlyBird.pricePlaceholder")}
            />
          </FormField>
          <FormField label={t("tickets.pricing.earlyBird.untilLabel")}>
            <Input
              type="datetime-local"
              value={ebUntil}
              onChange={(event) => setEbUntil(event.target.value)}
            />
          </FormField>
        </div>
        <div className="flex gap-2">
          <Button
            type="button"
            size="sm"
            onClick={() => void handleSaveEarlyBird()}
            disabled={savingEb}
            loading={savingEb}
            loadingLabel={t("tickets.pricing.saving")}
          >
            {t("tickets.pricing.earlyBird.save")}
          </Button>
          <Button
            type="button"
            size="sm"
            variant="ghost"
            onClick={() => {
              setEbPrice("");
              setEbUntil("");
            }}
            disabled={savingEb || (!ebPrice && !ebUntil)}
            loadingLabel=""
          >
            {t("tickets.pricing.earlyBird.clear")}
          </Button>
        </div>
      </section>

      {/* Group tiers */}
      <section className="flex flex-col gap-2">
        <p className="text-sm font-medium">{t("tickets.pricing.tiers.heading")}</p>
        <p className="text-xs text-muted">{t("tickets.pricing.tiers.help")}</p>
        <ul className="flex flex-col gap-2">
          {tierRows.map((row, index) => (
            <li key={index} className="flex items-end gap-2">
              <FormField label={t("tickets.pricing.tiers.minQtyLabel")}>
                <Input
                  inputMode="numeric"
                  value={row.minQty}
                  onChange={(event) => updateTier(index, { minQty: event.target.value })}
                  placeholder={t("tickets.pricing.tiers.minQtyPlaceholder")}
                />
              </FormField>
              <FormField label={t("tickets.pricing.tiers.priceLabel")}>
                <Input
                  inputMode="decimal"
                  value={row.priceZmw}
                  onChange={(event) => updateTier(index, { priceZmw: event.target.value })}
                  placeholder={t("tickets.pricing.tiers.pricePlaceholder")}
                />
              </FormField>
              <Button
                type="button"
                size="sm"
                variant="ghost"
                onClick={() => removeTier(index)}
                loadingLabel=""
              >
                {t("tickets.pricing.tiers.remove")}
              </Button>
            </li>
          ))}
        </ul>
        <div className="flex gap-2">
          <Button type="button" size="sm" variant="secondary" onClick={addTier} loadingLabel="">
            {t("tickets.pricing.tiers.add")}
          </Button>
          <Button
            type="button"
            size="sm"
            onClick={() => void handleSaveTiers()}
            disabled={savingTiers}
            loading={savingTiers}
            loadingLabel={t("tickets.pricing.saving")}
          >
            {t("tickets.pricing.tiers.save")}
          </Button>
        </div>
      </section>
    </div>
  );
}
