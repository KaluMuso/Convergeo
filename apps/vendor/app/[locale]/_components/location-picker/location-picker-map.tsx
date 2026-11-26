"use client";

import "leaflet/dist/leaflet.css";

import { useEffect, useRef } from "react";

import type { Map as LeafletMap, Marker as LeafletMarker } from "leaflet";

export const LUSAKA_CENTER = { lat: -15.4167, lng: 28.2833 };
const DEFAULT_ZOOM = 13;

type LocationPickerMapProps = {
  lat: number;
  lng: number;
  onPinMove: (lat: number, lng: number) => void;
  disabled?: boolean;
};

export function LocationPickerMap({ lat, lng, onPinMove, disabled }: LocationPickerMapProps) {
  const containerRef = useRef<HTMLDivElement | null>(null);
  const mapRef = useRef<LeafletMap | null>(null);
  const markerRef = useRef<LeafletMarker | null>(null);

  useEffect(() => {
    let cancelled = false;

    void (async () => {
      const leaflet = await import("leaflet");
      if (cancelled || !containerRef.current || mapRef.current) {
        return;
      }

      const iconBase = "https://unpkg.com/leaflet@1.9.4/dist/images";
      leaflet.Icon.Default.mergeOptions({
        iconRetinaUrl: `${iconBase}/marker-icon-2x.png`,
        iconUrl: `${iconBase}/marker-icon.png`,
        shadowUrl: `${iconBase}/marker-shadow.png`,
      });

      const map = leaflet.map(containerRef.current, {
        center: [lat, lng],
        zoom: DEFAULT_ZOOM,
        scrollWheelZoom: !disabled,
      });
      leaflet
        .tileLayer("https://tile.openstreetmap.org/{z}/{x}/{y}.png", {
          attribution: "© OpenStreetMap contributors",
          maxZoom: 19,
        })
        .addTo(map);

      const marker = leaflet.marker([lat, lng], { draggable: !disabled }).addTo(map);
      marker.on("dragend", () => {
        const position = marker.getLatLng();
        onPinMove(position.lat, position.lng);
      });

      mapRef.current = map;
      markerRef.current = marker;
    })();

    return () => {
      cancelled = true;
      mapRef.current?.remove();
      mapRef.current = null;
      markerRef.current = null;
    };
  }, [disabled, lat, lng, onPinMove]);

  useEffect(() => {
    if (!mapRef.current || !markerRef.current) {
      return;
    }
    markerRef.current.setLatLng([lat, lng]);
    mapRef.current.panTo([lat, lng], { animate: true, duration: 0.25 });
  }, [lat, lng]);

  return (
    <div
      ref={containerRef}
      className="h-52 w-full rounded-lg border border-border"
      data-testid="location-picker-map"
    />
  );
}
