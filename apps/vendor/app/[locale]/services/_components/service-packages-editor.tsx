"use client";

import { useSession } from "@vergeo/auth/use-session";
import { ApiError } from "@vergeo/config";
import { useTranslations } from "next-intl";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import { ngweeToZmwInput } from "../../listings/[id]/edit/_lib/money";
import { OFFER_FIELDS, OFFER_META, type Archetype, type AttributeErrors } from "../_lib/archetypes";
import {
  MAX_PACKAGES,
  PACKAGE_LIMITS,
  createPackagesClient,
  draftFromPackage,
  emptyDraft,
  validateDraft,
  type PackageDraft,
  type PackageField,
  type ServicePackage,
} from "../_lib/packages";
import { Button, FormField, Input } from "../_lib/ui";

import { AttributeFields } from "./attribute-fields";

type Props = {
  serviceId: string;
  /** Effective archetype of the service; decides the offer fields. */
  archetype?: Archetype;
  /** Service photos an offer can use as its own picture. */
  portfolioImages?: readonly string[];
};

/** One row of the editor: a saved package, an archived one, or a new unsaved draft. */
type Item = {
  key: string;
  pkg: ServicePackage | null;
  draft: PackageDraft | null;
  errors: Partial<Record<PackageField, string>>;
  attributeErrors: AttributeErrors;
  busy: boolean;
  message: string | null;
};

function apiErrorKey(error: unknown, fallback: string): string {
  if (error instanceof ApiError) {
    if (error.code === "prohibited_listing") return "errors.prohibited";
    if (error.code === "package_limit_reached") return "errors.limitReached";
    if (error.code === "package_order_mismatch") return "errors.orderMismatch";
    if (error.code === "rate_limited" || error.status === 429) return "errors.rateLimited";
    if (error.code === "conflict") return "errors.conflict";
  }
  return fallback;
}

/**
 * Vendor editor for an open list of up to 10 packages: add, edit, remove and
 * reorder. Validation mirrors the API so the vendor sees which field is wrong;
 * the API is still the gate (cap, ownership, content screen).
 */
export function ServicePackagesEditor({
  serviceId,
  archetype = "professional",
  portfolioImages = [],
}: Props) {
  const meta = OFFER_META[archetype];
  const t = useTranslations("services.vendor.packages");
  const { session } = useSession();
  const getToken = useCallback(() => session?.access_token ?? null, [session?.access_token]);
  const client = useMemo(() => createPackagesClient(getToken), [getToken]);
  const [loadFailed, setLoadFailed] = useState(false);
  const [loaded, setLoaded] = useState(false);
  const [items, setItems] = useState<Item[]>([]);
  const [listMessage, setListMessage] = useState<string | null>(null);
  const newKey = useRef(0);

  const patch = useCallback((key: string, next: Partial<Item>) => {
    setItems((prev) => prev.map((item) => (item.key === key ? { ...item, ...next } : item)));
  }, []);

  const hasSession = Boolean(session?.access_token);
  useEffect(() => {
    if (!hasSession) return;
    let cancelled = false;
    client
      .list(serviceId)
      .then((response) => {
        if (cancelled) return;
        setItems(
          response.items.map((pkg) => ({
            key: pkg.id,
            pkg,
            draft:
              pkg.status === "active" ? draftFromPackage(pkg, ngweeToZmwInput, archetype) : null,
            errors: {},
            attributeErrors: {},
            busy: false,
            message: null,
          })),
        );
        setLoaded(true);
      })
      .catch(() => {
        if (!cancelled) setLoadFailed(true);
      });
    return () => {
      cancelled = true;
    };
  }, [client, serviceId, hasSession, archetype]);

  // Counts what would be active: saved active packages plus any draft being edited.
  const activeCount = items.filter((item) => item.draft !== null).length;
  const limitReached = activeCount >= MAX_PACKAGES;

  const add = useCallback(() => {
    newKey.current += 1;
    setListMessage(null);
    setItems((prev) => [
      ...prev,
      {
        key: `new-${newKey.current}`,
        pkg: null,
        draft: emptyDraft(archetype),
        errors: {},
        attributeErrors: {},
        busy: false,
        message: null,
      },
    ]);
  }, [archetype]);

  const save = useCallback(
    async (item: Item) => {
      if (!item.draft) return;
      const verdict = validateDraft(item.draft, archetype);
      if (!verdict.ok) {
        patch(item.key, {
          errors: verdict.errors,
          attributeErrors: verdict.attributeErrors ?? {},
          message: null,
        });
        return;
      }
      patch(item.key, { busy: true, errors: {}, attributeErrors: {}, message: null });
      try {
        const pkg = item.pkg
          ? await client.update(serviceId, item.pkg.id, verdict.payload)
          : await client.create(serviceId, verdict.payload);
        patch(item.key, { pkg, busy: false, message: t("saved") });
      } catch (error) {
        patch(item.key, {
          busy: false,
          message: t(apiErrorKey(error, "errors.saveFailed"), {
            max: MAX_PACKAGES,
          }),
        });
      }
    },
    [archetype, client, patch, serviceId, t],
  );

  const remove = useCallback(
    async (item: Item) => {
      if (!item.pkg) {
        setItems((prev) => prev.filter((other) => other.key !== item.key));
        return;
      }
      patch(item.key, { busy: true, message: null });
      try {
        await client.remove(serviceId, item.pkg.id);
        setItems((prev) => prev.filter((other) => other.key !== item.key));
      } catch (error) {
        patch(item.key, {
          busy: false,
          message: t(apiErrorKey(error, "errors.archiveFailed")),
        });
      }
    },
    [client, patch, serviceId, t],
  );

  const move = useCallback(
    async (key: string, direction: -1 | 1) => {
      const savedActive = items.filter((item) => item.pkg?.status === "active");
      const at = savedActive.findIndex((item) => item.key === key);
      const neighbour = savedActive[at + direction];
      const current = savedActive[at];
      if (!current || !neighbour) return;
      const swap = (list: Item[]): Item[] =>
        list.map((item) =>
          item.key === current.key ? neighbour : item.key === neighbour.key ? current : item,
        );
      const previous = items;
      setListMessage(null);
      setItems(swap(items));
      const ids = swap(savedActive).map((item) => (item.pkg as ServicePackage).id);
      try {
        await client.reorder(serviceId, ids);
      } catch (error) {
        setItems(previous);
        setListMessage(t(apiErrorKey(error, "errors.reorderFailed")));
      }
    },
    [client, items, serviceId, t],
  );

  if (loadFailed) {
    return <p className="text-sm text-danger">{t("errors.loadFailed")}</p>;
  }
  if (!loaded) {
    return null;
  }

  const movable = items.filter((item) => item.pkg?.status === "active");

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
        <p className="text-sm text-text-2">{t("intro", { max: MAX_PACKAGES })}</p>
        <p className="text-xs text-text-3">{t("codNote")}</p>
        <p className="text-xs text-text-3">{t("guidance.fromPrice")}</p>
        <p role="status" className="text-sm font-medium text-text" data-testid="packages-count">
          {t("count", { count: activeCount, max: MAX_PACKAGES })}
        </p>
        {limitReached ? (
          <p role="status" className="text-sm text-text-2" data-testid="packages-limit-reached">
            {t("limitReached", { max: MAX_PACKAGES })}
          </p>
        ) : null}
        {listMessage ? (
          <p role="status" className="text-sm text-danger" data-testid="packages-list-message">
            {listMessage}
          </p>
        ) : null}
      </div>

      {items.map((item, index) => {
        const draft = item.draft;
        const fieldError = (field: PackageField) =>
          item.errors[field] ? t(item.errors[field] as string) : undefined;
        const setDraft = (next: Partial<PackageDraft>) =>
          patch(item.key, { draft: { ...(draft ?? emptyDraft(archetype)), ...next } });
        const label = draft?.name.trim() || item.pkg?.name || t("newPackage");
        const position = movable.findIndex((other) => other.key === item.key);
        const id = item.key;

        return (
          <div
            key={item.key}
            className="flex flex-col gap-3 rounded-2 border border-border bg-surface p-4"
            data-testid={`package-panel-${id}`}
          >
            <div className="flex flex-wrap items-center justify-between gap-2">
              <h3 className="font-semibold text-text">
                {t("packageHeading", { number: index + 1 })}
                <span className="ml-2 font-normal text-text-2">{label}</span>
              </h3>
              {item.pkg?.status === "active" ? (
                <span className="flex gap-2">
                  <Button
                    type="button"
                    variant="secondary"
                    loadingLabel={t("saving")}
                    disabled={item.busy || position <= 0}
                    aria-label={t("moveUp", { name: label })}
                    data-testid={`package-up-${id}`}
                    onClick={() => void move(item.key, -1)}
                  >
                    ↑
                  </Button>
                  <Button
                    type="button"
                    variant="secondary"
                    loadingLabel={t("saving")}
                    disabled={item.busy || position < 0 || position >= movable.length - 1}
                    aria-label={t("moveDown", { name: label })}
                    data-testid={`package-down-${id}`}
                    onClick={() => void move(item.key, 1)}
                  >
                    ↓
                  </Button>
                </span>
              ) : null}
              {!draft ? <span className="text-xs text-text-3">{t("archived")}</span> : null}
            </div>

            {!draft ? (
              <div className="flex flex-wrap gap-2">
                <Button
                  type="button"
                  variant="secondary"
                  loadingLabel={t("saving")}
                  disabled={item.busy || limitReached}
                  data-testid={`package-offer-${id}`}
                  onClick={() =>
                    patch(item.key, {
                      draft: item.pkg
                        ? draftFromPackage(item.pkg, ngweeToZmwInput, archetype)
                        : emptyDraft(archetype),
                      message: null,
                    })
                  }
                >
                  {t("offer")}
                </Button>
                <Button
                  type="button"
                  variant="secondary"
                  loadingLabel={t("saving")}
                  disabled={item.busy}
                  data-testid={`package-archive-${id}`}
                  onClick={() => void remove(item)}
                >
                  {t("archive")}
                </Button>
              </div>
            ) : (
              <form
                className="flex flex-col gap-3"
                onSubmit={(event) => {
                  event.preventDefault();
                  void save(item);
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
                    data-testid={`package-name-${id}`}
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

                <AttributeFields
                  scope="offer"
                  idPrefix={`offer-${id}`}
                  defs={OFFER_FIELDS[archetype]}
                  values={draft.attributes}
                  errors={item.attributeErrors}
                  portfolioImages={portfolioImages}
                  disabled={item.busy}
                  onChange={(attributes) => setDraft({ attributes })}
                />

                <fieldset className="flex flex-col gap-2">
                  <legend className="text-sm font-medium text-text">{t("priceModeLabel")}</legend>
                  <div className="flex flex-wrap gap-4 text-sm text-text">
                    {(["fixed", "quote"] as const).map((mode) => (
                      <label key={mode} className="flex min-h-11 items-center gap-2">
                        <input
                          type="radio"
                          name={`price-mode-${id}`}
                          checked={draft.priceMode === mode}
                          data-testid={`package-price-mode-${mode}-${id}`}
                          onChange={() => setDraft({ priceMode: mode })}
                        />
                        {mode === "fixed" ? t("priceModeFixed") : t("priceModeQuote")}
                      </label>
                    ))}
                  </div>
                </fieldset>
                {draft.priceMode === "fixed" ? (
                  <FormField
                    label={t("priceLabel")}
                    helpText={t(`priceUnit.${meta.priceUnit}`)}
                    errorMessage={fieldError("price")}
                  >
                    <Input
                      value={draft.price}
                      inputMode="decimal"
                      data-testid={`package-price-${id}`}
                      onChange={(event) => setDraft({ price: event.target.value })}
                    />
                  </FormField>
                ) : null}

                {meta.showDelivery ? (
                  <>
                    <FormField label={t("deliveryLabel")} errorMessage={fieldError("delivery")}>
                      <Input
                        value={draft.deliveryDays}
                        inputMode="numeric"
                        data-testid={`package-delivery-${id}`}
                        onChange={(event) => setDraft({ deliveryDays: event.target.value })}
                      />
                    </FormField>

                    <label className="flex min-h-11 items-center gap-2 text-sm text-text">
                      <input
                        type="checkbox"
                        checked={!draft.revisionsApplicable}
                        onChange={(event) =>
                          setDraft({ revisionsApplicable: !event.target.checked })
                        }
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
                  </>
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

                {fieldError("attributes") ? (
                  <p role="alert" className="text-sm text-danger">
                    {fieldError("attributes")}
                  </p>
                ) : null}

                {item.message ? (
                  <p
                    role="status"
                    className="text-sm text-text-2"
                    data-testid={`package-message-${id}`}
                  >
                    {item.message}
                  </p>
                ) : null}

                <div className="flex flex-wrap gap-2">
                  <Button
                    type="submit"
                    variant="primary"
                    loading={item.busy}
                    loadingLabel={t("saving")}
                    disabled={item.busy}
                    data-testid={`package-save-${id}`}
                  >
                    {t("save")}
                  </Button>
                  <Button
                    type="button"
                    variant="secondary"
                    loadingLabel={t("saving")}
                    disabled={item.busy}
                    data-testid={`package-archive-${id}`}
                    onClick={() => void remove(item)}
                  >
                    {t("archive")}
                  </Button>
                </div>
              </form>
            )}
          </div>
        );
      })}

      <div>
        <Button
          type="button"
          variant="secondary"
          loadingLabel={t("saving")}
          disabled={limitReached}
          data-testid="package-add"
          onClick={add}
        >
          {t("addPackage")}
        </Button>
      </div>
    </section>
  );
}
