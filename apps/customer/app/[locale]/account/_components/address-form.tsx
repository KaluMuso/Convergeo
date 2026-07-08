"use client";

import { Button } from "@vergeo/ui/src/button";
import { FormField } from "@vergeo/ui/src/form-field";
import { Input } from "@vergeo/ui/src/input";
import { useRouter } from "next/navigation";
import { useCallback, useState } from "react";

import { createAccountApiClient, type Address, type AddressInput } from "./account-api";
import { StaticMapPreview } from "./static-map-preview";

export type AddressFormLabels = {
  label: string;
  labelPlaceholder: string;
  landmark: string;
  landmarkPlaceholder: string;
  landmarkHelp: string;
  phone: string;
  phonePlaceholder: string;
  latitude: string;
  longitude: string;
  coordsHelp: string;
  useGps: string;
  gpsLoading: string;
  gpsDenied: string;
  gpsUnavailable: string;
  mapPreview: string;
  mapAlt: string;
  mapEmpty: string;
  coordsTemplate: string;
  save: string;
  saving: string;
  cancel: string;
  requiredLandmark: string;
  error: string;
  required: string;
};

type AddressFormProps = {
  locale: string;
  accessToken: string;
  labels: AddressFormLabels;
  initial?: Address;
  onCancel: () => void;
  onSaved: () => void;
};

function parseCoordinate(value: string): number | null {
  const trimmed = value.trim();
  if (!trimmed) {
    return null;
  }
  const parsed = Number(trimmed);
  return Number.isFinite(parsed) ? parsed : null;
}

export function AddressForm({
  locale,
  accessToken,
  labels,
  initial,
  onCancel,
  onSaved,
}: AddressFormProps) {
  const router = useRouter();
  const api = createAccountApiClient(() => accessToken);

  const [label, setLabel] = useState(initial?.label ?? "");
  const [landmark, setLandmark] = useState(initial?.landmark ?? "");
  const [phone, setPhone] = useState(initial?.phone ?? "");
  const [lat, setLat] = useState(initial?.lat?.toString() ?? "");
  const [lng, setLng] = useState(initial?.lng?.toString() ?? "");
  const [gpsDenied, setGpsDenied] = useState(false);
  const [gpsLoading, setGpsLoading] = useState(false);
  const [landmarkError, setLandmarkError] = useState<string | undefined>();
  const [formError, setFormError] = useState<string | undefined>();
  const [saving, setSaving] = useState(false);

  const latValue = parseCoordinate(lat);
  const lngValue = parseCoordinate(lng);

  const captureGps = useCallback(() => {
    setGpsDenied(false);
    if (typeof navigator === "undefined" || !navigator.geolocation) {
      setGpsDenied(true);
      return;
    }

    setGpsLoading(true);
    navigator.geolocation.getCurrentPosition(
      (position) => {
        setLat(position.coords.latitude.toFixed(6));
        setLng(position.coords.longitude.toFixed(6));
        setGpsDenied(false);
        setGpsLoading(false);
      },
      () => {
        setGpsDenied(true);
        setGpsLoading(false);
      },
      { enableHighAccuracy: true, timeout: 10_000 },
    );
  }, []);

  const handleSubmit = async (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setFormError(undefined);

    const trimmedLandmark = landmark.trim();
    if (!trimmedLandmark) {
      setLandmarkError(labels.requiredLandmark);
      return;
    }
    setLandmarkError(undefined);

    const payload: AddressInput = {
      label: label.trim() || null,
      landmark: trimmedLandmark,
      lat: latValue,
      lng: lngValue,
      phone: phone.trim() || null,
    };

    setSaving(true);
    try {
      if (initial) {
        await api.patchAddress(initial.id, payload);
      } else {
        await api.createAddress(payload);
      }
      onSaved();
      router.refresh();
    } catch {
      setFormError(labels.error);
    } finally {
      setSaving(false);
    }
  };

  return (
    <form className="space-y-4" onSubmit={(event) => void handleSubmit(event)} noValidate>
      <FormField label={labels.label}>
        <Input
          value={label}
          onChange={(event) => setLabel(event.target.value)}
          placeholder={labels.labelPlaceholder}
          autoComplete="address-line1"
        />
      </FormField>

      <FormField
        label={labels.landmark}
        helpText={labels.landmarkHelp}
        errorMessage={landmarkError}
        required
        requiredMarker={labels.required}
      >
        <Input
          value={landmark}
          onChange={(event) => setLandmark(event.target.value)}
          placeholder={labels.landmarkPlaceholder}
          error={Boolean(landmarkError)}
          required
        />
      </FormField>

      <FormField label={labels.phone}>
        <Input
          value={phone}
          onChange={(event) => setPhone(event.target.value)}
          placeholder={labels.phonePlaceholder}
          inputMode="tel"
          autoComplete="tel"
        />
      </FormField>

      <div className="space-y-2">
        <div className="flex flex-wrap items-center gap-3">
          <Button
            type="button"
            variant="secondary"
            loading={gpsLoading}
            loadingLabel={labels.gpsLoading}
            onClick={captureGps}
          >
            {labels.useGps}
          </Button>
          {gpsDenied ? (
            <p className="text-sm text-warning" role="status">
              {typeof navigator !== "undefined" && navigator.geolocation
                ? labels.gpsDenied
                : labels.gpsUnavailable}
            </p>
          ) : null}
        </div>
        <p className="text-sm font-medium text-text">{labels.mapPreview}</p>
        <StaticMapPreview
          lat={latValue}
          lng={lngValue}
          emptyLabel={labels.mapEmpty}
          coordsLabel={
            latValue !== null && lngValue !== null
              ? labels.coordsTemplate
                  .replace("{lat}", latValue.toFixed(5))
                  .replace("{lng}", lngValue.toFixed(5))
              : undefined
          }
          alt={labels.mapAlt
            .replace("{lat}", latValue?.toFixed(5) ?? "—")
            .replace("{lng}", lngValue?.toFixed(5) ?? "—")}
        />
      </div>

      <div className="grid grid-cols-2 gap-3">
        <FormField label={labels.latitude} helpText={labels.coordsHelp}>
          <Input
            value={lat}
            onChange={(event) => setLat(event.target.value)}
            inputMode="decimal"
            aria-label={labels.latitude}
          />
        </FormField>
        <FormField label={labels.longitude}>
          <Input
            value={lng}
            onChange={(event) => setLng(event.target.value)}
            inputMode="decimal"
            aria-label={labels.longitude}
          />
        </FormField>
      </div>

      {formError ? (
        <p className="text-sm text-danger" role="alert">
          {formError}
        </p>
      ) : null}

      <div className="flex flex-wrap gap-3 pt-2">
        <Button type="submit" loading={saving} loadingLabel={labels.saving}>
          {labels.save}
        </Button>
        <Button
          type="button"
          variant="secondary"
          loading={false}
          loadingLabel={labels.saving}
          onClick={onCancel}
        >
          {labels.cancel}
        </Button>
      </div>
      <span className="sr-only">{locale}</span>
    </form>
  );
}
