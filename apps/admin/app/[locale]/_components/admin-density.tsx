"use client";

import { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";

export type AdminDensity = "comfortable" | "compact";

const STORAGE_KEY = "vergeo5-admin-density";

type AdminDensityContextValue = {
  density: AdminDensity;
  setDensity: (next: AdminDensity) => void;
  toggleDensity: () => void;
};

const AdminDensityContext = createContext<AdminDensityContextValue | null>(null);

function readStoredDensity(): AdminDensity {
  if (typeof window === "undefined") {
    return "comfortable";
  }
  try {
    const raw = window.localStorage.getItem(STORAGE_KEY);
    return raw === "compact" ? "compact" : "comfortable";
  } catch {
    return "comfortable";
  }
}

export function AdminDensityProvider({ children }: { children: React.ReactNode }) {
  const [density, setDensityState] = useState<AdminDensity>("comfortable");

  useEffect(() => {
    setDensityState(readStoredDensity());
  }, []);

  useEffect(() => {
    document.documentElement.dataset.adminDensity = density;
  }, [density]);

  const setDensity = useCallback((next: AdminDensity) => {
    setDensityState(next);
    try {
      window.localStorage.setItem(STORAGE_KEY, next);
    } catch {
      /* ignore quota / private mode */
    }
  }, []);

  const toggleDensity = useCallback(() => {
    setDensity(density === "compact" ? "comfortable" : "compact");
  }, [density, setDensity]);

  const value = useMemo(
    () => ({ density, setDensity, toggleDensity }),
    [density, setDensity, toggleDensity],
  );

  return <AdminDensityContext.Provider value={value}>{children}</AdminDensityContext.Provider>;
}

export function useAdminDensity(): AdminDensityContextValue {
  const ctx = useContext(AdminDensityContext);
  if (!ctx) {
    throw new Error("useAdminDensity must be used within AdminDensityProvider");
  }
  return ctx;
}
