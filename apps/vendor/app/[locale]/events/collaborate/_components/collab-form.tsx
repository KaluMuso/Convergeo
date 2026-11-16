"use client";

import { useRouter } from "next/navigation";
import { useTranslations } from "next-intl";
import { useEffect, useMemo, useState } from "react";

import {
  Button,
  FormField,
  Input,
  Select,
  Textarea,
} from "../../../listings/new/_lib/ui";
import {
  createEventsClient,
  type EventCategoryOption,
} from "../../_lib/events-client";
import {
  type CollabRequest,
  type OrganiserOption,
} from "../_lib/collab-client";
import {
  EQUIPMENT_ITEMS,
  bpsToPercent,
  kwachaToNgwee,
  ngweeToKwachaText,
  normaliseChecklist,
  normaliseDraft,
  parsePercentInput,
  readinessPct,
  submitErrors,
  type Checklist,
  type EquipmentItem,
  type EquipmentState,
  type EventDraftFields,
  type FieldError,
  type PermitState,
} from "../_lib/collab-readiness";

import {
  FieldErrorList,
  ReadinessMeter,
  fieldErrorsFromApi,
  useCollabClient,
  useCollabErrorText,
} from "./collab-parts";

type Props = {
  locale: string;
  /** Present in edit mode (draft / changes_requested). */
  request?: CollabRequest;
  onSaved?: (request: CollabRequest) => void;
};

function toLocalInput(iso: string | null): string {
  if (!iso) return "";
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return "";
  const pad = (n: number) => String(n).padStart(2, "0");
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}T${pad(date.getHours())}:${pad(date.getMinutes())}`;
}

function fromLocalInput(value: string): string | null {
  if (!value) return null;
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? null : date.toISOString();
}

function numberOrNull(value: string): number | null {
  const trimmed = value.trim();
  if (!trimmed) return null;
  const n = Number(trimmed);
  return Number.isFinite(n) ? n : null;
}

function Section({
  id,
  title,
  children,
}: {
  id: string;
  title: string;
  children: React.ReactNode;
}) {
  return (
    <section
      data-testid={`collab-section-${id}`}
      className="flex flex-col gap-3 rounded-xl border border-border bg-surface p-4"
    >
      <h2 className="text-sm font-semibold uppercase tracking-wide text-text-3">
        {title}
      </h2>
      {children}
    </section>
  );
}

export function CollabForm({ locale, request, onSaved }: Props) {
  const t = useTranslations("vendor");
  const te = useTranslations("events");
  const router = useRouter();
  const { client, hasSession } = useCollabClient();
  const errorText = useCollabErrorText();

  const editing = Boolean(request);
  const [draft, setDraft] = useState<EventDraftFields>(
    normaliseDraft(request?.event_draft),
  );
  const [checklist, setChecklist] = useState<Checklist>(
    normaliseChecklist(request?.checklist),
  );
  const [shareText, setShareText] = useState(
    request?.revenue_share_bps != null
      ? String(bpsToPercent(request.revenue_share_bps))
      : "",
  );
  const [organiser, setOrganiser] = useState<OrganiserOption | null>(null);
  const [query, setQuery] = useState("");
  const [organisers, setOrganisers] = useState<OrganiserOption[]>([]);
  const [categories, setCategories] = useState<EventCategoryOption[]>([]);
  const [busy, setBusy] = useState<"save" | "submit" | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [fieldErrors, setFieldErrors] = useState<FieldError[]>([]);
  const [shareInvalid, setShareInvalid] = useState(false);

  const shareBps = parsePercentInput(shareText);
  const pct = readinessPct(checklist, shareBps);

  // Categories (public endpoint; leaf categories only).
  useEffect(() => {
    let cancelled = false;
    createEventsClient(() => null)
      .listCategories()
      .then((rows) => {
        if (!cancelled) setCategories(rows);
      })
      .catch(() => undefined);
    return () => {
      cancelled = true;
    };
  }, []);
  const leafCategories = useMemo(() => {
    const parents = new Set(
      categories.map((c) => c.parent_slug).filter(Boolean),
    );
    return categories.filter((c) => !parents.has(c.slug));
  }, [categories]);

  // Organiser search (create mode only).
  useEffect(() => {
    if (editing || !hasSession) return;
    let cancelled = false;
    const handle = setTimeout(() => {
      client
        .listOrganisers(query)
        .then((response) => {
          if (!cancelled) setOrganisers(response.items);
        })
        .catch((caught: unknown) => {
          if (!cancelled) setError(errorText(caught));
        });
    }, 250);
    return () => {
      cancelled = true;
      clearTimeout(handle);
    };
  }, [client, editing, hasSession, query, errorText]);

  const patchChecklist = (patch: Partial<Checklist>) =>
    setChecklist((current) => ({ ...current, ...patch }));

  const payload = () => ({
    event_draft: draft,
    checklist,
    revenue_share_bps: shareBps,
  });

  const save = async (andSubmit: boolean) => {
    setError(null);
    setMessage(null);
    setFieldErrors([]);
    if (shareText.trim() && shareBps === null) {
      setShareInvalid(true);
      return;
    }
    setShareInvalid(false);
    if (!editing && !organiser) {
      setError(t("events.collab.errors.pickOrganiser"));
      return;
    }
    if (andSubmit) {
      const blockers = submitErrors(draft, checklist, shareBps);
      if (blockers.length > 0) {
        setFieldErrors(blockers);
        return;
      }
    }
    setBusy(andSubmit ? "submit" : "save");
    try {
      let saved: CollabRequest = editing
        ? await client.updateRequest(request!.id, payload())
        : await client.createRequest(organiser!.vendor_id, payload());
      if (andSubmit) {
        saved = await client.submit(saved.id);
        setMessage(t("events.collab.form.submitted"));
      } else {
        setMessage(t("events.collab.form.saved"));
      }
      if (onSaved) {
        onSaved(saved);
      }
      if (!editing) {
        router.replace(`/${locale}/events/collaborate/${saved.id}`);
      }
    } catch (caught) {
      setFieldErrors(fieldErrorsFromApi(caught));
      setError(errorText(caught));
    } finally {
      setBusy(null);
    }
  };

  const equipmentOptions: EquipmentState[] = ["ready", "needed", "not_needed"];
  const permitOptions: PermitState[] = ["obtained", "pending", "not_required"];
  const setEquipment = (item: EquipmentItem, value: string) =>
    patchChecklist({
      equipment: {
        ...checklist.equipment,
        [item]: (value || null) as EquipmentState | null,
      },
    });

  const useMyLocation = () => {
    if (!("geolocation" in navigator)) return;
    navigator.geolocation.getCurrentPosition(
      (pos) =>
        patchChecklist({
          venue: {
            ...checklist.venue,
            lat: Number(pos.coords.latitude.toFixed(6)),
            lng: Number(pos.coords.longitude.toFixed(6)),
          },
        }),
      () => setError(t("events.collab.checklist.venue.locationFailed")),
    );
  };

  return (
    <form
      className="flex flex-col gap-4"
      data-testid="collab-form"
      onSubmit={(event) => {
        event.preventDefault();
        void save(false);
      }}
    >
      <header className="flex flex-col gap-1">
        <h1 className="text-xl font-semibold text-text">
          {editing
            ? t("events.collab.form.editTitle")
            : t("events.collab.form.title")}
        </h1>
        <p className="text-sm text-text-2">{t("events.collab.form.intro")}</p>
      </header>

      <div className="sticky top-0 z-10 bg-bg py-2">
        <ReadinessMeter pct={pct} />
      </div>

      {!editing ? (
        <Section id="organiser" title={t("events.collab.sections.organiser")}>
          <FormField label={t("events.collab.form.organiser.search")}>
            <Input
              type="search"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              data-testid="collab-organiser-search"
            />
          </FormField>
          {organisers.length === 0 ? (
            <p className="text-sm text-text-2">
              {t("events.collab.form.organiser.none")}
            </p>
          ) : (
            <ul
              className="flex flex-col gap-2"
              role="radiogroup"
              aria-label={t("events.collab.sections.organiser")}
            >
              {organisers.map((option) => (
                <li key={option.vendor_id}>
                  <label className="flex min-h-11 cursor-pointer items-start gap-3 rounded-lg border border-border p-3">
                    <input
                      type="radio"
                      name="organiser"
                      checked={organiser?.vendor_id === option.vendor_id}
                      onChange={() => setOrganiser(option)}
                      data-testid={`collab-organiser-${option.vendor_id}`}
                    />
                    <span className="flex flex-col">
                      <span className="font-medium text-text">
                        {option.display_name}
                      </span>
                      {option.blurb ? (
                        <span className="text-xs text-text-2">
                          {option.blurb}
                        </span>
                      ) : null}
                    </span>
                  </label>
                </li>
              ))}
            </ul>
          )}
        </Section>
      ) : (
        <p className="text-sm text-text-2">
          {t("events.collab.form.organiser.fixed", {
            name: request?.organiser.display_name ?? "",
          })}
        </p>
      )}

      <Section id="event" title={t("events.collab.sections.event")}>
        <FormField label={t("events.collab.form.event.title")}>
          <Input
            value={draft.title ?? ""}
            maxLength={200}
            onChange={(e) => setDraft({ ...draft, title: e.target.value })}
            data-testid="collab-title"
          />
        </FormField>
        <FormField label={t("events.collab.form.event.category")}>
          <Select
            value={draft.category ?? ""}
            onChange={(e) =>
              setDraft({ ...draft, category: e.target.value || null })
            }
            data-testid="collab-category"
          >
            <option value="">
              {t("events.collab.form.event.categoryPlaceholder")}
            </option>
            {leafCategories.map((c) => (
              <option key={c.slug} value={c.slug}>
                {te(c.label_key.replace(/^events\./, ""))}
              </option>
            ))}
          </Select>
        </FormField>
        <FormField label={t("events.collab.form.event.city")}>
          <Input
            value={draft.city ?? ""}
            maxLength={80}
            onChange={(e) => setDraft({ ...draft, city: e.target.value })}
          />
        </FormField>
        <FormField label={t("events.collab.form.event.description")}>
          <Textarea
            value={draft.description ?? ""}
            maxLength={4000}
            onChange={(e) =>
              setDraft({ ...draft, description: e.target.value })
            }
          />
        </FormField>
      </Section>

      <Section id="venue" title={t("events.collab.sections.venue")}>
        <FormField label={t("events.collab.checklist.venue.name")}>
          <Input
            value={checklist.venue.name ?? ""}
            maxLength={200}
            onChange={(e) =>
              patchChecklist({
                venue: { ...checklist.venue, name: e.target.value || null },
              })
            }
            data-testid="collab-venue-name"
          />
        </FormField>
        <FormField label={t("events.collab.checklist.venue.landmark")}>
          <Input
            value={checklist.venue.landmark ?? ""}
            maxLength={200}
            onChange={(e) =>
              patchChecklist({
                venue: { ...checklist.venue, landmark: e.target.value || null },
              })
            }
          />
        </FormField>
        <div className="grid grid-cols-2 gap-3">
          <FormField label={t("events.collab.checklist.venue.lat")}>
            <Input
              inputMode="decimal"
              value={checklist.venue.lat ?? ""}
              onChange={(e) =>
                patchChecklist({
                  venue: {
                    ...checklist.venue,
                    lat: numberOrNull(e.target.value),
                  },
                })
              }
              data-testid="collab-venue-lat"
            />
          </FormField>
          <FormField label={t("events.collab.checklist.venue.lng")}>
            <Input
              inputMode="decimal"
              value={checklist.venue.lng ?? ""}
              onChange={(e) =>
                patchChecklist({
                  venue: {
                    ...checklist.venue,
                    lng: numberOrNull(e.target.value),
                  },
                })
              }
              data-testid="collab-venue-lng"
            />
          </FormField>
        </div>
        <Button
          type="button"
          variant="secondary"
          loadingLabel={t("events.collab.loading")}
          onClick={useMyLocation}
        >
          {t("events.collab.checklist.venue.useLocation")}
        </Button>
      </Section>

      <Section id="schedule" title={t("events.collab.sections.schedule")}>
        <FormField label={t("events.collab.checklist.schedule.starts")}>
          <Input
            type="datetime-local"
            value={toLocalInput(checklist.schedule.starts_at)}
            onChange={(e) =>
              patchChecklist({
                schedule: {
                  ...checklist.schedule,
                  starts_at: fromLocalInput(e.target.value),
                },
              })
            }
            data-testid="collab-starts"
          />
        </FormField>
        <FormField label={t("events.collab.checklist.schedule.ends")}>
          <Input
            type="datetime-local"
            value={toLocalInput(checklist.schedule.ends_at)}
            onChange={(e) =>
              patchChecklist({
                schedule: {
                  ...checklist.schedule,
                  ends_at: fromLocalInput(e.target.value),
                },
              })
            }
            data-testid="collab-ends"
          />
        </FormField>
      </Section>

      <Section id="capacity" title={t("events.collab.sections.capacity")}>
        <FormField label={t("events.collab.checklist.capacity.label")}>
          <Input
            inputMode="numeric"
            value={checklist.capacity.capacity ?? ""}
            onChange={(e) => {
              const n = numberOrNull(e.target.value);
              patchChecklist({
                capacity: {
                  capacity:
                    n !== null && Number.isInteger(n) && n > 0 ? n : null,
                },
              });
            }}
            data-testid="collab-capacity"
          />
        </FormField>
      </Section>

      <Section id="equipment" title={t("events.collab.sections.equipment")}>
        <p className="text-sm text-text-2">
          {t("events.collab.checklist.equipment.help")}
        </p>
        {EQUIPMENT_ITEMS.map((item) => (
          <FormField
            key={item}
            label={t(`events.collab.checklist.equipment.items.${item}`)}
          >
            <Select
              value={checklist.equipment[item] ?? ""}
              onChange={(e) => setEquipment(item, e.target.value)}
              data-testid={`collab-equipment-${item}`}
            >
              <option value="">{t("events.collab.checklist.choose")}</option>
              {equipmentOptions.map((state) => (
                <option key={state} value={state}>
                  {t(`events.collab.checklist.equipment.states.${state}`)}
                </option>
              ))}
            </Select>
          </FormField>
        ))}
      </Section>

      <Section id="permits" title={t("events.collab.sections.permits")}>
        <p className="text-sm text-text-2">
          {t("events.collab.checklist.permits.help")}
        </p>
        <FormField label={t("events.collab.checklist.permits.label")}>
          <Select
            value={checklist.permits.status ?? ""}
            onChange={(e) =>
              patchChecklist({
                permits: {
                  ...checklist.permits,
                  status: (e.target.value || null) as PermitState | null,
                },
              })
            }
            data-testid="collab-permits"
          >
            <option value="">{t("events.collab.checklist.choose")}</option>
            {permitOptions.map((state) => (
              <option key={state} value={state}>
                {t(`events.collab.checklist.permits.states.${state}`)}
              </option>
            ))}
          </Select>
        </FormField>
        <FormField label={t("events.collab.checklist.permits.note")}>
          <Input
            value={checklist.permits.note ?? ""}
            maxLength={500}
            onChange={(e) =>
              patchChecklist({
                permits: { ...checklist.permits, note: e.target.value || null },
              })
            }
          />
        </FormField>
      </Section>

      <Section id="tiers" title={t("events.collab.sections.tiers")}>
        {checklist.tiers.map((tier, index) => (
          <div
            key={index}
            className="flex flex-col gap-2 rounded-lg border border-border p-3"
          >
            <FormField label={t("events.collab.checklist.tiers.name")}>
              <Input
                value={tier.name}
                maxLength={80}
                onChange={(e) =>
                  patchChecklist({
                    tiers: checklist.tiers.map((x, i) =>
                      i === index ? { ...x, name: e.target.value } : x,
                    ),
                  })
                }
                data-testid={`collab-tier-name-${index}`}
              />
            </FormField>
            <div className="grid grid-cols-2 gap-3">
              <FormField label={t("events.collab.checklist.tiers.price")}>
                <Input
                  inputMode="decimal"
                  defaultValue={ngweeToKwachaText(tier.price_ngwee)}
                  onChange={(e) => {
                    const ngwee = kwachaToNgwee(e.target.value);
                    if (ngwee === null) return;
                    patchChecklist({
                      tiers: checklist.tiers.map((x, i) =>
                        i === index ? { ...x, price_ngwee: ngwee } : x,
                      ),
                    });
                  }}
                  data-testid={`collab-tier-price-${index}`}
                />
              </FormField>
              <FormField label={t("events.collab.checklist.tiers.qty")}>
                <Input
                  inputMode="numeric"
                  value={tier.qty_cap ?? ""}
                  onChange={(e) => {
                    const n = numberOrNull(e.target.value);
                    patchChecklist({
                      tiers: checklist.tiers.map((x, i) =>
                        i === index
                          ? {
                              ...x,
                              qty_cap:
                                n !== null && Number.isInteger(n) && n > 0
                                  ? n
                                  : null,
                            }
                          : x,
                      ),
                    });
                  }}
                />
              </FormField>
            </div>
            <Button
              type="button"
              variant="ghost"
              loadingLabel={t("events.collab.loading")}
              onClick={() =>
                patchChecklist({
                  tiers: checklist.tiers.filter((_, i) => i !== index),
                })
              }
            >
              {t("events.collab.checklist.tiers.remove")}
            </Button>
          </div>
        ))}
        {checklist.tiers.length < 10 ? (
          <Button
            type="button"
            variant="secondary"
            loadingLabel={t("events.collab.loading")}
            data-testid="collab-tier-add"
            onClick={() =>
              patchChecklist({
                tiers: [
                  ...checklist.tiers,
                  { name: "", price_ngwee: 0, qty_cap: null },
                ],
              })
            }
          >
            {t("events.collab.checklist.tiers.add")}
          </Button>
        ) : null}
      </Section>

      <Section id="share" title={t("events.collab.sections.share")}>
        <p className="text-sm text-text-2">
          {t("events.collab.checklist.share.help")}
        </p>
        <FormField
          label={t("events.collab.checklist.share.label")}
          errorMessage={
            shareInvalid
              ? t("events.collab.checklist.share.invalid")
              : undefined
          }
        >
          <Input
            inputMode="decimal"
            value={shareText}
            onChange={(e) => setShareText(e.target.value)}
            data-testid="collab-share"
          />
        </FormField>
        {shareBps !== null ? (
          <p className="text-xs text-text-2" data-testid="collab-share-bps">
            {t("events.collab.checklist.share.preview", {
              cohost: bpsToPercent(shareBps),
              organiser: bpsToPercent(10_000 - shareBps),
            })}
          </p>
        ) : null}
      </Section>

      <FieldErrorList errors={fieldErrors} />
      {error ? (
        <p
          role="alert"
          className="text-sm text-danger"
          data-testid="collab-error"
        >
          {error}
        </p>
      ) : null}
      {message ? (
        <p
          role="status"
          className="text-sm text-success"
          data-testid="collab-message"
        >
          {message}
        </p>
      ) : null}

      <div className="flex flex-col gap-2">
        <Button
          type="submit"
          variant="secondary"
          loading={busy === "save"}
          loadingLabel={t("events.collab.form.saving")}
          disabled={busy !== null}
          data-testid="collab-save"
        >
          {t("events.collab.form.saveDraft")}
        </Button>
        <Button
          type="button"
          loading={busy === "submit"}
          loadingLabel={t("events.collab.form.submitting")}
          disabled={busy !== null}
          onClick={() => void save(true)}
          data-testid="collab-submit"
        >
          {t("events.collab.form.submit")}
        </Button>
      </div>
    </form>
  );
}
