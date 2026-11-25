"use client";

import { ApiError } from "@vergeo/config";
import dynamic from "next/dynamic";
import { useTranslations } from "next-intl";
import { useCallback, useMemo, useState } from "react";

import { Button, FormField, Input } from "../../listings/new/_lib/ui";

import { createGeoClient } from "./geo-client";
import { LUSAKA_CENTER } from "./location-picker-map";

const LocationPickerMap = dynamic(
  () => import("./location-picker-map").then((mod) => mod.LocationPickerMap),
  { ssr: false, loading: () => <div className="h-52 animate-pulse rounded-lg bg-bg-2" /> },
);

export type LocationPickerValue = {
  lat: string;
  lng: string;
  landmark: string;
};

type LocationPickerProps = {
  value: LocationPickerValue;
  onChange: (value: LocationPickerValue) => void;
  getToken: () => string | null | Promise<string | null>;
  disabled?: boolean;
  landmarkRequired?: boolean;
};

function formatCoord(value: number): string {
  return value.toFixed(6);
}

export function LocationPicker({
  value,
  onChange,
  getToken,
  disabled = false,
  landmarkRequired = true,
}: LocationPickerProps) {
  const t = useTranslations("vendor");
  const geoClient = useMemo(() => createGeoClient(getToken), [getToken]);
  const [geoBusy, setGeoBusy] = useState(false);
  const [accuracyM, setAccuracyM] = useState<number | null>(null);
  const [geoError, setGeoError] = useState<string | null>(null);
  const [searchQuery, setSearchQuery] = useState("");
  const [searchBusy, setSearchBusy] = useState(false);
  const [searchError, setSearchError] = useState<string | null>(null);
  const [searchResults, setSearchResults] = useState<
    Array<{ label: string; lat: number; lng: number }>
  >([]);
  const [advancedOpen, setAdvancedOpen] = useState(false);

  const parsedLat = Number.parseFloat(value.lat);
  const parsedLng = Number.parseFloat(value.lng);
  const mapLat = Number.isFinite(parsedLat) ? parsedLat : LUSAKA_CENTER.lat;
  const mapLng = Number.isFinite(parsedLng) ? parsedLng : LUSAKA_CENTER.lng;

  const patch = useCallback(
    (patchValue: Partial<LocationPickerValue>) => {
      onChange({ ...value, ...patchValue });
    },
    [onChange, value],
  );

  const useCurrentLocation = () => {
    setGeoError(null);
    setAccuracyM(null);
    if (!("geolocation" in navigator)) {
      setGeoError(t("profile.location.geoUnsupported"));
      return;
    }
    setGeoBusy(true);
    navigator.geolocation.getCurrentPosition(
      (position) => {
        patch({
          lat: formatCoord(position.coords.latitude),
          lng: formatCoord(position.coords.longitude),
        });
        setAccuracyM(Math.round(position.coords.accuracy));
        setGeoBusy(false);
      },
      (error) => {
        setGeoBusy(false);
        if (error.code === 1) {
          setGeoError(t("profile.location.geoDenied"));
        } else {
          setGeoError(t("profile.location.geoFailed"));
        }
      },
      { enableHighAccuracy: true, timeout: 15_000, maximumAge: 0 },
    );
  };

  const runSearch = async () => {
    const q = searchQuery.trim();
    if (q.length < 3) {
      setSearchError(t("profile.location.searchTooShort"));
      return;
    }
    setSearchBusy(true);
    setSearchError(null);
    setSearchResults([]);
    try {
      const results = await geoClient.search(q);
      setSearchResults(results.slice(0, 5));
      if (results.length === 0) {
        setSearchError(t("profile.location.searchEmpty"));
      }
    } catch (caught) {
      if (caught instanceof ApiError && caught.code === "geo_unavailable") {
        setSearchError(t("profile.location.searchUnavailable"));
      } else {
        setSearchError(t("profile.location.searchFailed"));
      }
    } finally {
      setSearchBusy(false);
    }
  };

  const applySearchResult = (result: { label: string; lat: number; lng: number }) => {
    patch({
      lat: formatCoord(result.lat),
      lng: formatCoord(result.lng),
    });
    setSearchResults([]);
    setSearchQuery(result.label);
  };

  return (
    <div className="space-y-3" data-testid="location-picker">
      <Button
        type="button"
        className="min-h-11 w-full"
        disabled={disabled || geoBusy}
        loading={geoBusy}
        loadingLabel={t("profile.location.locating")}
        onClick={useCurrentLocation}
      >
        {t("profile.location.useMyLocation")}
      </Button>
      {accuracyM != null ? (
        <p className="text-xs text-text-2">
          {t("profile.location.accuracy", { metres: accuracyM })}
        </p>
      ) : null}
      {geoError ? (
        <p className="text-sm text-text-2" role="status">
          {geoError}
        </p>
      ) : null}

      <FormField label={t("profile.location.searchLabel")}>
        <div className="flex gap-2">
          <Input
            value={searchQuery}
            onChange={(event) => setSearchQuery(event.target.value)}
            disabled={disabled || searchBusy}
            placeholder={t("profile.location.searchPlaceholder")}
            onKeyDown={(event) => {
              if (event.key === "Enter") {
                event.preventDefault();
                void runSearch();
              }
            }}
          />
          <Button
            type="button"
            variant="secondary"
            disabled={disabled || searchBusy}
            loading={searchBusy}
            loadingLabel={t("profile.location.searching")}
            onClick={() => void runSearch()}
          >
            {t("profile.location.searchAction")}
          </Button>
        </div>
      </FormField>
      {searchError ? (
        <p className="text-sm text-text-2" role="status">
          {searchError}
        </p>
      ) : null}
      {searchResults.length > 0 ? (
        <ul className="space-y-1 rounded-lg border border-border bg-surface p-2">
          {searchResults.map((result) => (
            <li key={`${result.lat}:${result.lng}:${result.label}`}>
              <button
                type="button"
                className="w-full rounded px-2 py-2 text-left text-sm text-text hover:bg-bg-2"
                disabled={disabled}
                onClick={() => applySearchResult(result)}
              >
                {result.label}
              </button>
            </li>
          ))}
        </ul>
      ) : null}

      <LocationPickerMap
        lat={mapLat}
        lng={mapLng}
        disabled={disabled}
        onPinMove={(lat, lng) => patch({ lat: formatCoord(lat), lng: formatCoord(lng) })}
      />
      <p className="text-micro text-text-3">{t("profile.location.mapAttribution")}</p>

      <FormField label={t("profile.fields.landmarkLabel")}>
        <Input
          value={value.landmark}
          onChange={(event) => patch({ landmark: event.target.value })}
          disabled={disabled}
          required={landmarkRequired}
          placeholder={t("profile.fields.landmarkPlaceholder")}
        />
      </FormField>

      <details
        className="rounded-lg border border-border bg-bg-2 p-3"
        open={advancedOpen}
        onToggle={(event) => setAdvancedOpen((event.target as HTMLDetailsElement).open)}
      >
        <summary className="cursor-pointer text-sm font-medium text-text">
          {t("profile.location.advanced")}
        </summary>
        <div className="mt-3 grid grid-cols-2 gap-3">
          <FormField label={t("profile.fields.latLabel")}>
            <Input
              inputMode="decimal"
              value={value.lat}
              onChange={(event) => patch({ lat: event.target.value })}
              disabled={disabled}
              placeholder={t("profile.fields.latPlaceholder")}
            />
          </FormField>
          <FormField label={t("profile.fields.lngLabel")}>
            <Input
              inputMode="decimal"
              value={value.lng}
              onChange={(event) => patch({ lng: event.target.value })}
              disabled={disabled}
              placeholder={t("profile.fields.lngPlaceholder")}
            />
          </FormField>
        </div>
      </details>
      <p className="text-xs text-text-3">{t("profile.fields.locationHelp")}</p>
    </div>
  );
}
