"use client";

import { createApiClient } from "@vergeo/config";
import { useEffect, useRef, useState } from "react";

import { getApiBaseUrl } from "../../../../../lib/api-base-url";
import { buildCategoryTree, type CategoryRecord, type NavCategory } from "../category-tree";
import { buildStaticMegaMenuRoots } from "../mega-menu-static-categories";

import { FALLBACK_ROOT_SLUGS } from "./labels";

/** Re-fetch at most this often; the API itself caches for an hour. */
export const MENU_TREE_TTL_MS = 10 * 60 * 1000;
export const MENU_TREE_STORAGE_KEY = "vergeo5:menu-tree:v1";

type CacheEntry = { at: number; tree: NavCategory[] };

let memory: CacheEntry | null = null;
let inflight: Promise<NavCategory[]> | null = null;

export function resetMenuTreeCacheForTests(): void {
  memory = null;
  inflight = null;
  try {
    window.sessionStorage.removeItem(MENU_TREE_STORAGE_KEY);
  } catch {
    // ignore
  }
}

function readSession(): CacheEntry | null {
  try {
    const raw = window.sessionStorage.getItem(MENU_TREE_STORAGE_KEY);
    if (!raw) {
      return null;
    }
    const parsed = JSON.parse(raw) as Partial<CacheEntry>;
    if (typeof parsed.at === "number" && Array.isArray(parsed.tree)) {
      return { at: parsed.at, tree: parsed.tree };
    }
  } catch {
    // ignore
  }
  return null;
}

function writeSession(entry: CacheEntry): void {
  try {
    window.sessionStorage.setItem(MENU_TREE_STORAGE_KEY, JSON.stringify(entry));
  } catch {
    // ignore
  }
}

function fallbackTree(labels: Record<string, string>): NavCategory[] {
  const bySlug: Record<string, string> = {};
  for (const slug of FALLBACK_ROOT_SLUGS) {
    const name = labels[slug];
    if (name) {
      bySlug[slug] = name;
    }
  }
  return buildStaticMegaMenuRoots(bySlug);
}

type PublicCategoryRow = CategoryRecord & { path?: string };

async function fetchTree(fallbackLabels: Record<string, string>): Promise<NavCategory[]> {
  const baseUrl = getApiBaseUrl();
  if (!baseUrl) {
    return fallbackTree(fallbackLabels);
  }
  try {
    const client = createApiClient({ baseUrl });
    const rows = await client.request<PublicCategoryRow[]>("/categories");
    if (!Array.isArray(rows)) {
      return fallbackTree(fallbackLabels);
    }
    const tree = buildCategoryTree(
      rows.map((row) => ({
        id: row.id,
        name: row.name,
        slug: row.slug,
        position: row.position,
        parent_id: row.parent_id,
        prohibited: row.prohibited,
      })),
    );
    return tree.length > 0 ? tree : fallbackTree(fallbackLabels);
  } catch {
    return fallbackTree(fallbackLabels);
  }
}

/**
 * Stale-while-revalidate category tree shared by the desktop panel and the
 * mobile drawer: module memory → sessionStorage → network. Only real network
 * results are cached (fallbacks are retried on the next open).
 */
export async function loadMenuTree(
  fallbackLabels: Record<string, string>,
  now: number = Date.now(),
): Promise<NavCategory[]> {
  const cached = memory ?? readSession();
  if (cached && now - cached.at < MENU_TREE_TTL_MS) {
    memory = cached;
    return cached.tree;
  }
  if (!inflight) {
    inflight = fetchTree(fallbackLabels)
      .then((tree) => {
        const isFallback = tree.some((root) => root.id.startsWith("static:"));
        if (!isFallback) {
          memory = { at: Date.now(), tree };
          writeSession(memory);
        }
        return tree;
      })
      .finally(() => {
        inflight = null;
      });
  }
  const fresh = inflight;
  // Stale entry: show it immediately, refresh in the background.
  if (cached) {
    void fresh.catch(() => undefined);
    return cached.tree;
  }
  return fresh;
}

export type MenuTreeState = { tree: NavCategory[] | null; loading: boolean };

export function useMenuTree(
  active: boolean,
  fallbackLabels: Record<string, string>,
  loader?: () => Promise<NavCategory[]>,
): MenuTreeState {
  const [tree, setTree] = useState<NavCategory[] | null>(null);
  const [loading, setLoading] = useState(false);
  const labelsRef = useRef(fallbackLabels);
  labelsRef.current = fallbackLabels;
  const loaderRef = useRef(loader);
  loaderRef.current = loader;
  const startedRef = useRef(false);
  const mountedRef = useRef(true);

  useEffect(() => {
    mountedRef.current = true;
    return () => {
      mountedRef.current = false;
    };
  }, []);

  useEffect(() => {
    if (!active || startedRef.current) {
      return;
    }
    startedRef.current = true;
    setLoading(true);
    const run = loaderRef.current ? loaderRef.current() : loadMenuTree(labelsRef.current);
    void run
      .then((next) => {
        if (mountedRef.current) setTree(next);
      })
      .catch(() => {
        if (mountedRef.current) setTree(fallbackTree(labelsRef.current));
      })
      .finally(() => {
        if (mountedRef.current) setLoading(false);
      });
  }, [active]);

  return { tree, loading };
}
