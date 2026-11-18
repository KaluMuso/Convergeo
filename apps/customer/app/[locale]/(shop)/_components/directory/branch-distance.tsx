"use client";

import { useEffect, useState } from "react";

import { distanceMetres, readNearCoords } from "../../../../../lib/near-coords";

/**
 * "2.3 km away" for one branch card, only when the customer's location is
 * known in this tab (URL ?lat/lng or "Near me"). Renders nothing otherwise, so
 * the server-rendered card never depends on it. Templates come pre-translated.
 */
export function BranchDistance({
  lat,
  lng,
  kmTemplate,
  metresTemplate,
}: {
  lat: number;
  lng: number;
  /** e.g. "{km} km away" */
  kmTemplate: string;
  /** e.g. "{m} m away" */
  metresTemplate: string;
}) {
  const [label, setLabel] = useState<string | null>(null);

  useEffect(() => {
    const here = readNearCoords(window.location.search);
    if (!here) return;
    const metres = distanceMetres(here, { lat, lng });
    setLabel(
      metres < 1000
        ? metresTemplate.replace(
            "{m}",
            String(Math.max(10, Math.round(metres / 10) * 10)),
          )
        : kmTemplate.replace(
            "{km}",
            (Math.round(metres / 100) / 10).toFixed(1),
          ),
    );
  }, [kmTemplate, lat, lng, metresTemplate]);

  if (!label) return null;
  return (
    <span className="text-sm text-text-2" data-testid="branch-distance">
      {label}
    </span>
  );
}
