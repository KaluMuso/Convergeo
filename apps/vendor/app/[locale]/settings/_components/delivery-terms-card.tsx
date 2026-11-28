"use client";

import { useSession } from "@vergeo/auth/use-session";
import { formatK } from "@vergeo/i18n";
import { Radio } from "@vergeo/ui/src/radio";
import { useTranslations } from "next-intl";
import { useCallback, useEffect, useMemo, useState } from "react";

import {
  isValidZmwDecimal,
  ngweeToZmwInput,
  zmwDecimalToNgwee,
} from "../../listings/[id]/edit/_lib/money";
import { Button, Input, Switch } from "../../listings/new/_lib/ui";
import {
  createDeliveryTermsClient,
  deliveryErrorKey,
  type DeliveryTerms,
  type DeliveryTermsClient,
  type DeliveryTermsUpdate,
  type FreeDeliveryMethod,
} from "../_lib/delivery-terms-client";

type Props = { client?: DeliveryTermsClient };

const METHODS: FreeDeliveryMethod[] = ["platform_courier", "self_delivery"];

/**
 * Shop-wide free delivery. Turning it ON moves the delivery cost to the vendor,
 * so it always goes through an explicit confirm step that says who pays. Changes
 * only affect new orders (the server snapshots funding on each order).
 */
export function DeliveryTermsCard({ client: injected }: Props) {
  const t = useTranslations("vendor.settings.delivery");
  const { session } = useSession();
  const token = session?.access_token ?? null;
  const getToken = useCallback(() => token, [token]);
  const client = useMemo(
    () => injected ?? createDeliveryTermsClient(getToken),
    [injected, getToken],
  );

  const [terms, setTerms] = useState<DeliveryTerms | null>(null);
  const [loadFailed, setLoadFailed] = useState(false);
  const [saving, setSaving] = useState(false);
  // A change that moves delivery cost to the vendor waits here for an explicit yes.
  const [pending, setPending] = useState<DeliveryTermsUpdate | null>(null);
  const [minInput, setMinInput] = useState("");
  const [minInvalid, setMinInvalid] = useState(false);
  const [message, setMessage] = useState<{
    tone: "ok" | "error";
    key: string;
  } | null>(null);

  const hasToken = token !== null;
  useEffect(() => {
    if (!hasToken) return;
    let cancelled = false;
    client
      .get()
      .then((row) => {
        if (cancelled) return;
        setTerms(row);
        setMinInput(ngweeToZmwInput(row.free_delivery_min_ngwee));
      })
      .catch(() => {
        if (!cancelled) setLoadFailed(true);
      });
    return () => {
      cancelled = true;
    };
  }, [client, hasToken]);

  const save = useCallback(
    async (changes: DeliveryTermsUpdate) => {
      setSaving(true);
      setMessage(null);
      try {
        const next = await client.update(changes);
        setTerms(next);
        setMinInput(ngweeToZmwInput(next.free_delivery_min_ngwee));
        setMessage({ tone: "ok", key: "saved" });
      } catch (error) {
        setMessage({ tone: "error", key: deliveryErrorKey(error) });
      } finally {
        setSaving(false);
        setPending(null);
      }
    },
    [client],
  );

  if (loadFailed) {
    return (
      <p role="alert" className="text-sm text-danger">
        {t("loadFailed")}
      </p>
    );
  }
  if (!terms) {
    return <p className="text-sm text-text-2">{t("loading")}</p>;
  }

  const onToggle = (next: boolean) => {
    if (next) {
      // Turning on moves cost to the vendor: confirm first, never one tap.
      setPending({ free_delivery_all: true });
      setMessage(null);
      return;
    }
    setPending(null);
    void save({ free_delivery_all: false });
  };

  const onMethod = (method: FreeDeliveryMethod) => {
    if (method === terms.free_delivery_method) return;
    if (method === "platform_courier") {
      // A courier fee is charged to the vendor: confirm first.
      setPending({ free_delivery_method: method });
      setMessage(null);
      return;
    }
    setPending(null);
    void save({ free_delivery_method: method });
  };

  const floorLabel = formatK(terms.min_floor_ngwee);
  const onSaveMin = () => {
    if (!isValidZmwDecimal(minInput) || zmwDecimalToNgwee(minInput) < terms.min_floor_ngwee) {
      setMinInvalid(true);
      setMessage(null);
      return;
    }
    setMinInvalid(false);
    const ngwee = zmwDecimalToNgwee(minInput);
    if (ngwee !== terms.free_delivery_min_ngwee) void save({ free_delivery_min_ngwee: ngwee });
  };

  const confirmMethod = pending?.free_delivery_method ?? terms.free_delivery_method;

  return (
    <div className="flex flex-col gap-3" data-testid="delivery-terms">
      <p className="text-sm text-text-2">{t("intro")}</p>

      <Switch
        label={t("allToggle")}
        checked={
          pending?.free_delivery_all === true || (terms.free_delivery_all && pending === null)
        }
        disabled={saving}
        data-testid="delivery-all-toggle"
        onChange={(event) => onToggle(event.target.checked)}
      />
      <p className="text-xs text-text-2">{t("allHelp")}</p>

      <div className="flex flex-col gap-1">
        <label htmlFor="delivery-min-input" className="text-sm font-medium text-text">
          {t("minLabel")}
        </label>
        <div className="flex flex-wrap items-start gap-2">
          <Input
            id="delivery-min-input"
            inputMode="decimal"
            value={minInput}
            disabled={saving}
            error={minInvalid}
            aria-describedby="delivery-min-help"
            data-testid="delivery-min-input"
            onChange={(event) => {
              setMinInput(event.target.value);
              setMinInvalid(false);
            }}
          />
          <Button
            type="button"
            variant="secondary"
            disabled={saving}
            loadingLabel={t("confirm.working")}
            data-testid="delivery-min-save"
            onClick={onSaveMin}
          >
            {t("minSave")}
          </Button>
        </div>
        <p
          id="delivery-min-help"
          className={minInvalid ? "text-xs text-danger" : "text-xs text-text-2"}
          role={minInvalid ? "alert" : undefined}
          data-testid="delivery-min-help"
        >
          {minInvalid
            ? t("minInvalid", { floor: floorLabel })
            : t("minHelp", { floor: floorLabel })}
        </p>
      </div>

      <fieldset className="flex flex-col gap-1 border-0 p-0" disabled={saving}>
        <legend className="mb-1 text-sm font-medium text-text">{t("methodHeading")}</legend>
        {METHODS.map((method) => (
          <div key={method} className="flex flex-col">
            <Radio
              name="free-delivery-method"
              value={method}
              label={t(`method.${method}`)}
              checked={(pending?.free_delivery_method ?? terms.free_delivery_method) === method}
              data-testid={`delivery-method-${method}`}
              onChange={() => onMethod(method)}
            />
            <p className="ml-8 text-xs text-text-2">{t(`method.${method}_help`)}</p>
          </div>
        ))}
      </fieldset>

      {pending ? (
        <div
          role="alertdialog"
          aria-labelledby="delivery-confirm-title"
          data-testid="delivery-confirm"
          className="flex flex-col gap-2 rounded-lg border border-warning/50 bg-surface p-3"
        >
          <p id="delivery-confirm-title" className="text-sm font-semibold">
            {pending.free_delivery_all ? t("confirm.title") : t("confirm.methodTitle")}
          </p>
          <p className="text-sm text-text-2">
            {confirmMethod === "self_delivery" ? t("confirm.self") : t("confirm.courier")}
          </p>
          <p className="text-sm text-text-2" data-testid="delivery-confirm-min">
            {t("confirm.minNote", {
              min: formatK(terms.free_delivery_min_ngwee),
            })}
          </p>
          {confirmMethod === "platform_courier" && terms.zone_fees.length > 0 ? (
            <div data-testid="delivery-confirm-bands">
              <p className="text-sm font-medium text-text">{t("confirm.bandsHeading")}</p>
              <ul className="mt-1 list-none p-0 text-sm text-text-2">
                {terms.zone_fees.map((zone) => (
                  <li key={zone.zone_key}>
                    {t("confirm.band", {
                      label: zone.label,
                      fee: formatK(zone.fee_ngwee),
                    })}
                  </li>
                ))}
              </ul>
            </div>
          ) : null}
          <div className="flex flex-wrap gap-2">
            <Button
              type="button"
              loading={saving}
              loadingLabel={t("confirm.working")}
              data-testid="delivery-confirm-yes"
              onClick={() => void save(pending)}
            >
              {t("confirm.yes")}
            </Button>
            <Button
              type="button"
              variant="secondary"
              loadingLabel={t("confirm.working")}
              disabled={saving}
              data-testid="delivery-confirm-no"
              onClick={() => setPending(null)}
            >
              {t("confirm.no")}
            </Button>
          </div>
        </div>
      ) : null}

      {message ? (
        <p
          role={message.tone === "error" ? "alert" : "status"}
          className={message.tone === "error" ? "text-sm text-danger" : "text-sm text-text"}
          data-testid="delivery-message"
        >
          {t(message.key)}
        </p>
      ) : null}

      <p className="text-xs text-text-2">{t("listingsHint")}</p>
      <p className="text-xs text-text-2">{t("appliesNote")}</p>
    </div>
  );
}
