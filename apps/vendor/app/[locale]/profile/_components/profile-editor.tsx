"use client";

import { useSession } from "@vergeo/auth/use-session";
import { ApiError } from "@vergeo/config";
import { useTranslations } from "next-intl";
import { useCallback, useEffect, useMemo, useState } from "react";

import { Button, FormField, Input, Spinner, Switch } from "../../listings/new/_lib/ui";
import { createProfileClient } from "../_lib/profile-client";

import { CompletenessMeter } from "./completeness-meter";
import { CoverUpload } from "./cover-upload";
import { HoursEditor } from "./hours-editor";
import { LogoUpload } from "./logo-upload";
import { SlugField } from "./slug-field";

import type { ProfilePatchPayload, VendorProfile } from "../_lib/profile-client";

const DEFAULT_HOURS = {
  mon: { open: "08:00", close: "17:00", closed: false },
  tue: { open: "08:00", close: "17:00", closed: false },
  wed: { open: "08:00", close: "17:00", closed: false },
  thu: { open: "08:00", close: "17:00", closed: false },
  fri: { open: "08:00", close: "17:00", closed: false },
  sat: { open: "09:00", close: "13:00", closed: false },
  sun: { open: "09:00", close: "13:00", closed: true },
};

export function ProfileEditor() {
  const t = useTranslations("vendor");
  const { session, loading: sessionLoading } = useSession();
  const [profile, setProfile] = useState<VendorProfile | null>(null);
  const [displayName, setDisplayName] = useState("");
  const [description, setDescription] = useState("");
  const [whatsapp, setWhatsapp] = useState("");
  const [slug, setSlug] = useState("");
  const [logoUrl, setLogoUrl] = useState<string | null>(null);
  const [coverUrl, setCoverUrl] = useState<string | null>(null);
  const [hours, setHours] = useState<VendorProfile["hours"]>(DEFAULT_HOURS);
  const [lat, setLat] = useState("");
  const [lng, setLng] = useState("");
  const [landmark, setLandmark] = useState("");
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);

  const getToken = useCallback(() => session?.access_token ?? null, [session?.access_token]);
  const profileClient = useMemo(() => createProfileClient(getToken), [getToken]);

  useEffect(() => {
    if (sessionLoading) {
      return;
    }
    if (!session) {
      setLoading(false);
      return;
    }

    let cancelled = false;
    void profileClient
      .getProfile()
      .then((loaded) => {
        if (cancelled) {
          return;
        }
        setProfile(loaded);
        setDisplayName(loaded.display_name);
        setDescription(loaded.description ?? "");
        setWhatsapp(loaded.whatsapp_msisdn ?? "");
        setSlug(loaded.slug);
        setLogoUrl(loaded.logo_url);
        setCoverUrl(loaded.cover_url);
        setHours(Object.keys(loaded.hours).length > 0 ? loaded.hours : DEFAULT_HOURS);
        setLat(loaded.lat?.toString() ?? "");
        setLng(loaded.lng?.toString() ?? "");
        setLandmark(loaded.landmark ?? "");
      })
      .catch(() => {
        if (!cancelled) {
          setError(t("profile.errors.loadFailed"));
        }
      })
      .finally(() => {
        if (!cancelled) {
          setLoading(false);
        }
      });

    return () => {
      cancelled = true;
    };
  }, [profileClient, session, sessionLoading, t]);

  const handleSave = async () => {
    setSaving(true);
    setError(null);
    setSuccess(null);

    const payload: ProfilePatchPayload = {
      display_name: displayName.trim(),
      description: description.trim(),
      whatsapp_msisdn: whatsapp.trim(),
      logo_url: logoUrl ?? undefined,
      // Empty string (not undefined) so the remove button can clear the cover.
      cover_url: coverUrl ?? "",
      hours,
    };

    if (!profile?.slug_locked && slug.trim() && slug.trim() !== profile?.slug) {
      payload.slug = slug.trim();
    }

    const parsedLat = Number.parseFloat(lat);
    const parsedLng = Number.parseFloat(lng);
    if (Number.isFinite(parsedLat) && Number.isFinite(parsedLng) && landmark.trim()) {
      payload.location = {
        lat: parsedLat,
        lng: parsedLng,
        landmark: landmark.trim(),
      };
    }

    try {
      const updated = await profileClient.updateProfile(payload);
      setProfile(updated);
      setSlug(updated.slug);
      setWhatsapp(updated.whatsapp_msisdn ?? "");
      setCoverUrl(updated.cover_url);
      setSuccess(t("profile.success.saved"));
    } catch (caught) {
      if (caught instanceof ApiError) {
        const messageKey = caught.details.message_key;
        if (typeof messageKey === "string" && messageKey.startsWith("vendor.profile.errors.")) {
          const key = messageKey.replace("vendor.profile.errors.", "");
          setError(t(`profile.errors.${key}` as "profile.errors.saveFailed"));
        } else if (caught.code === "conflict") {
          setError(t("profile.errors.slug_locked"));
        } else {
          setError(t("profile.errors.saveFailed"));
        }
      } else {
        setError(t("profile.errors.saveFailed"));
      }
    } finally {
      setSaving(false);
    }
  };

  if (sessionLoading || loading) {
    return (
      <div className="flex min-h-[40vh] items-center justify-center">
        <Spinner label={t("profile.loading")} />
      </div>
    );
  }

  if (!session) {
    return (
      <p className="rounded-lg border border-neutral-200 bg-neutral-50 p-4 text-sm text-neutral-700">
        {t("profile.errors.authRequired")}
      </p>
    );
  }

  const completeness = profile?.completeness ?? {
    logo: false,
    description: false,
    hours: false,
    location: false,
    badge: false,
  };

  return (
    <div className="space-y-6">
      <header className="space-y-1">
        <h1 className="text-xl font-semibold text-neutral-900">{t("profile.title")}</h1>
        <p className="text-sm text-neutral-600">{t("profile.intro")}</p>
      </header>

      {profile ? (
        <CompletenessMeter score={profile.completeness_score} breakdown={completeness} />
      ) : null}

      <form
        className="space-y-5"
        onSubmit={(event) => {
          event.preventDefault();
          void handleSave();
        }}
      >
        <section className="space-y-3">
          <h2 className="text-sm font-semibold text-neutral-900">{t("profile.sections.basics")}</h2>
          <FormField label={t("profile.fields.displayNameLabel")}>
            <Input
              value={displayName}
              onChange={(event) => setDisplayName(event.target.value)}
              disabled={saving}
              required
            />
          </FormField>
          <SlugField
            slug={slug}
            slugLocked={profile?.slug_locked ?? false}
            previousSlug={profile?.previous_slug ?? null}
            disabled={saving}
            onChange={setSlug}
          />
          <FormField label={t("profile.fields.descriptionLabel")}>
            <textarea
              value={description}
              onChange={(event) => setDescription(event.target.value)}
              disabled={saving}
              rows={4}
              className="w-full rounded-lg border border-neutral-300 px-3 py-2 text-sm"
              placeholder={t("profile.fields.descriptionPlaceholder")}
            />
          </FormField>
          <p className="text-xs text-neutral-500">{t("profile.fields.descriptionHelp")}</p>
        </section>

        <section className="space-y-3">
          <h2 className="text-sm font-semibold text-neutral-900">
            {t("profile.sections.contact")}
          </h2>
          <FormField label={t("profile.fields.whatsappLabel")}>
            <Input
              type="tel"
              inputMode="tel"
              value={whatsapp}
              onChange={(event) => setWhatsapp(event.target.value)}
              disabled={saving}
              placeholder={t("profile.fields.whatsappPlaceholder")}
            />
          </FormField>
          <p className="text-xs text-neutral-500">{t("profile.fields.whatsappHelp")}</p>
        </section>

        <section className="space-y-3">
          <h2 className="text-sm font-semibold text-neutral-900">{t("profile.sections.cover")}</h2>
          <CoverUpload
            coverUrl={coverUrl}
            disabled={saving}
            getToken={getToken}
            onUploaded={setCoverUrl}
            onRemove={() => setCoverUrl(null)}
          />
        </section>

        <section className="space-y-3">
          <h2 className="text-sm font-semibold text-neutral-900">{t("profile.sections.logo")}</h2>
          <LogoUpload
            logoUrl={logoUrl}
            disabled={saving}
            getToken={getToken}
            onUploaded={setLogoUrl}
          />
        </section>

        <section className="space-y-3">
          <h2 className="text-sm font-semibold text-neutral-900">
            {t("profile.sections.location")}
          </h2>
          <FormField label={t("profile.fields.landmarkLabel")}>
            <Input
              value={landmark}
              onChange={(event) => setLandmark(event.target.value)}
              disabled={saving}
              placeholder={t("profile.fields.landmarkPlaceholder")}
            />
          </FormField>
          <div className="grid grid-cols-2 gap-3">
            <FormField label={t("profile.fields.latLabel")}>
              <Input
                inputMode="decimal"
                value={lat}
                onChange={(event) => setLat(event.target.value)}
                disabled={saving}
                placeholder={t("profile.fields.latPlaceholder")}
              />
            </FormField>
            <FormField label={t("profile.fields.lngLabel")}>
              <Input
                inputMode="decimal"
                value={lng}
                onChange={(event) => setLng(event.target.value)}
                disabled={saving}
                placeholder={t("profile.fields.lngPlaceholder")}
              />
            </FormField>
          </div>
          <p className="text-xs text-neutral-500">{t("profile.fields.locationHelp")}</p>
        </section>

        <section>
          <HoursEditor hours={hours} disabled={saving} onChange={setHours} />
        </section>

        {profile?.preferred_badge ? (
          <div className="rounded-lg border border-emerald-200 bg-emerald-50 p-3 text-sm text-emerald-800">
            <Switch checked disabled label={t("profile.badge.preferred")} />
          </div>
        ) : (
          <p className="text-sm text-neutral-600">{t("profile.badge.hint")}</p>
        )}

        {error ? <p className="text-sm text-red-600">{error}</p> : null}
        {success ? <p className="text-sm text-emerald-700">{success}</p> : null}

        <Button
          type="submit"
          disabled={saving}
          loading={saving}
          loadingLabel={t("profile.actions.saving")}
          className="min-h-11 w-full"
        >
          {t("profile.actions.save")}
        </Button>
      </form>
    </div>
  );
}
