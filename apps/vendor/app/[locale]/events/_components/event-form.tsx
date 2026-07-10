"use client";

import { useSession } from "@vergeo/auth/use-session";
import { ApiError } from "@vergeo/config";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useTranslations } from "next-intl";
import { useCallback, useEffect, useMemo, useState } from "react";

import {
  createEventsClient,
  type EventCategory,
  type EventCreatePayload,
  type EventDetail,
} from "../_lib/events-client";
import { Button, FormField, Input, Select, Spinner } from "../_lib/ui";

import { EventImagePicker } from "./image-picker";
import {
  draftToPayload,
  InstanceEditor,
  toInstanceDraft,
  type InstanceDraft,
} from "./instance-editor";

const CATEGORIES: EventCategory[] = [
  "workshops",
  "comedy-theatre",
  "pop-up-dinners",
  "cultural-arts",
  "lifestyle-community",
  "free-rsvp",
];

type EventFormProps = {
  locale: string;
  mode: "create" | "edit";
  eventId?: string;
  initialEvent?: EventDetail;
};

export function EventForm({ locale, mode, eventId, initialEvent }: EventFormProps) {
  const t = useTranslations("vendor");
  const te = useTranslations("events");
  const router = useRouter();
  const { session, loading: sessionLoading } = useSession();

  const [title, setTitle] = useState(initialEvent?.title ?? "");
  const [category, setCategory] = useState<EventCategory>(initialEvent?.category ?? "workshops");
  const [description, setDescription] = useState(initialEvent?.description ?? "");
  const [venue, setVenue] = useState(initialEvent?.venue ?? "");
  const [landmark, setLandmark] = useState(initialEvent?.landmark ?? "");
  const [lat, setLat] = useState(initialEvent?.lat?.toString() ?? "");
  const [lng, setLng] = useState(initialEvent?.lng?.toString() ?? "");
  const [images, setImages] = useState<string[]>(initialEvent?.images ?? []);
  const [instances, setInstances] = useState<InstanceDraft[]>(
    initialEvent?.instances.length
      ? initialEvent.instances.map((row) => toInstanceDraft(row))
      : [toInstanceDraft()],
  );
  const [status, setStatus] = useState(initialEvent?.status ?? "draft");
  const [ticketsSold, setTicketsSold] = useState(initialEvent?.tickets_sold ?? 0);
  const [saving, setSaving] = useState(false);
  const [actionLoading, setActionLoading] = useState<"publish" | "cancel" | "end" | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  const getToken = useCallback(() => session?.access_token ?? null, [session?.access_token]);
  const eventsClient = useMemo(() => createEventsClient(getToken), [getToken]);

  useEffect(() => {
    if (!initialEvent) {
      return;
    }
    setTitle(initialEvent.title);
    setCategory(initialEvent.category ?? "workshops");
    setDescription(initialEvent.description ?? "");
    setVenue(initialEvent.venue ?? "");
    setLandmark(initialEvent.landmark ?? "");
    setLat(initialEvent.lat?.toString() ?? "");
    setLng(initialEvent.lng?.toString() ?? "");
    setImages(initialEvent.images);
    setInstances(initialEvent.instances.map((row) => toInstanceDraft(row)));
    setStatus(initialEvent.status);
    setTicketsSold(initialEvent.tickets_sold);
  }, [initialEvent]);

  const buildPayload = (): EventCreatePayload => ({
    title: title.trim(),
    category,
    description: description.trim() || null,
    venue: venue.trim() || null,
    landmark: landmark.trim() || null,
    lat: lat.trim() ? Number.parseFloat(lat) : null,
    lng: lng.trim() ? Number.parseFloat(lng) : null,
    images,
    instances: draftToPayload(instances),
  });

  const handleSave = async () => {
    if (!title.trim()) {
      setError(t("events.errors.required"));
      return;
    }

    setSaving(true);
    setError(null);
    setNotice(null);

    try {
      const payload = buildPayload();
      if (mode === "create") {
        const created = await eventsClient.createEvent(payload);
        router.push(`/${locale}/events/${created.event.id}/edit`);
        return;
      }
      if (!eventId) {
        return;
      }
      const updated = await eventsClient.updateEvent(eventId, payload);
      setStatus(updated.event.status);
      setTicketsSold(updated.event.tickets_sold);
      setInstances(updated.event.instances.map((row) => toInstanceDraft(row)));
      setNotice(t("events.form.saved"));
    } catch (caught) {
      if (caught instanceof ApiError) {
        const messageKey = caught.details.message_key;
        if (typeof messageKey === "string" && messageKey.startsWith("vendor.events.errors.")) {
          const key = messageKey.replace("vendor.events.", "") as
            "errors.required" | "errors.capacity_below_sold" | "errors.past_instance";
          setError(t(`events.${key}`));
          return;
        }
      }
      setError(t("events.errors.saveFailed"));
    } finally {
      setSaving(false);
    }
  };

  const runAction = async (action: "publish" | "cancel" | "end") => {
    if (!eventId) {
      return;
    }
    setActionLoading(action);
    setError(null);
    setNotice(null);
    try {
      const response =
        action === "publish"
          ? await eventsClient.publishEvent(eventId)
          : action === "cancel"
            ? await eventsClient.cancelEvent(eventId)
            : await eventsClient.endEvent(eventId);
      setStatus(response.event.status);
      setNotice(t(`events.actions.${action}Success`));
    } catch {
      setError(t("events.errors.actionFailed"));
    } finally {
      setActionLoading(null);
    }
  };

  if (sessionLoading) {
    return (
      <div className="flex min-h-[40vh] items-center justify-center">
        <Spinner label={t("events.list.loading")} />
      </div>
    );
  }

  if (!session) {
    return <p className="text-sm text-muted-foreground">{t("events.errors.authRequired")}</p>;
  }

  const readOnly = status === "cancelled" || status === "completed";

  return (
    <div className="flex flex-col gap-6">
      <header className="space-y-1">
        <p className="text-xs uppercase tracking-wide text-muted-foreground">
          {t("events.eyebrow")}
        </p>
        <h1 className="text-xl font-semibold text-foreground">
          {mode === "create" ? t("events.form.createTitle") : t("events.form.editTitle")}
        </h1>
        {mode === "edit" ? (
          <p className="text-sm text-muted-foreground">
            {t(`events.status.${status}`)}
            {ticketsSold > 0 ? ` · ${t("events.form.ticketsSold", { count: ticketsSold })}` : ""}
          </p>
        ) : null}
      </header>

      <FormField label={t("events.form.title")} required requiredMarker="*">
        <Input
          value={title}
          onChange={(event) => setTitle(event.target.value)}
          placeholder={t("events.form.titlePlaceholder")}
          disabled={readOnly || saving}
          required
        />
      </FormField>

      <FormField label={te("filters.categoryLabel")} required requiredMarker="*">
        <Select
          value={category}
          onChange={(event) => setCategory(event.target.value as EventCategory)}
          disabled={readOnly || saving}
        >
          {CATEGORIES.map((value) => (
            <option key={value} value={value}>
              {te(`categories.${value}`)}
            </option>
          ))}
        </Select>
      </FormField>

      <FormField label={t("events.form.description")}>
        <textarea
          className="min-h-24 w-full rounded-md border border-input bg-background px-3 py-2 text-sm"
          value={description}
          onChange={(event) => setDescription(event.target.value)}
          placeholder={t("events.form.descriptionPlaceholder")}
          disabled={readOnly || saving}
        />
      </FormField>

      <FormField label={t("events.form.venue")}>
        <Input
          value={venue}
          onChange={(event) => setVenue(event.target.value)}
          placeholder={t("events.form.venuePlaceholder")}
          disabled={readOnly || saving}
        />
      </FormField>

      <FormField label={t("events.form.landmark")}>
        <Input
          value={landmark}
          onChange={(event) => setLandmark(event.target.value)}
          placeholder={t("events.form.landmarkPlaceholder")}
          disabled={readOnly || saving}
        />
      </FormField>

      <div className="grid grid-cols-2 gap-3">
        <FormField label={t("events.form.lat")}>
          <Input
            value={lat}
            onChange={(event) => setLat(event.target.value)}
            placeholder={t("events.form.latPlaceholder")}
            disabled={readOnly || saving}
          />
        </FormField>
        <FormField label={t("events.form.lng")}>
          <Input
            value={lng}
            onChange={(event) => setLng(event.target.value)}
            placeholder={t("events.form.lngPlaceholder")}
            disabled={readOnly || saving}
          />
        </FormField>
      </div>

      <EventImagePicker
        images={images}
        getToken={getToken}
        onChange={setImages}
        disabled={readOnly || saving}
      />

      <InstanceEditor instances={instances} onChange={setInstances} disabled={readOnly || saving} />

      {error ? <p className="text-sm text-destructive">{error}</p> : null}
      {notice ? <p className="text-sm text-emerald-700">{notice}</p> : null}

      <div className="flex flex-col gap-2">
        {!readOnly ? (
          <Button
            type="button"
            onClick={() => void handleSave()}
            disabled={saving || actionLoading !== null}
            loading={saving}
            loadingLabel={t("events.form.saving")}
          >
            {t("events.form.save")}
          </Button>
        ) : null}

        {mode === "edit" && status === "draft" ? (
          <Button
            type="button"
            variant="secondary"
            onClick={() => void runAction("publish")}
            disabled={saving || actionLoading !== null}
            loading={actionLoading === "publish"}
            loadingLabel={t("events.actions.publishing")}
          >
            {t("events.actions.publish")}
          </Button>
        ) : null}

        {mode === "edit" && status === "published" ? (
          <>
            <Button
              type="button"
              variant="secondary"
              onClick={() => void runAction("end")}
              disabled={saving || actionLoading !== null}
              loading={actionLoading === "end"}
              loadingLabel={t("events.actions.ending")}
            >
              {t("events.actions.end")}
            </Button>
            <Button
              type="button"
              variant="ghost"
              onClick={() => void runAction("cancel")}
              disabled={saving || actionLoading !== null}
              loading={actionLoading === "cancel"}
              loadingLabel={t("events.actions.cancelling")}
            >
              {t("events.actions.cancel")}
            </Button>
          </>
        ) : null}

        {mode === "edit" && status === "draft" ? (
          <Button
            type="button"
            variant="ghost"
            onClick={() => void runAction("cancel")}
            disabled={saving || actionLoading !== null}
            loading={actionLoading === "cancel"}
            loadingLabel={t("events.actions.cancelling")}
          >
            {t("events.actions.cancel")}
          </Button>
        ) : null}

        <Link
          href={`/${locale}/events`}
          className="text-center text-sm text-muted-foreground underline"
        >
          {t("events.form.backToList")}
        </Link>
      </div>
    </div>
  );
}
