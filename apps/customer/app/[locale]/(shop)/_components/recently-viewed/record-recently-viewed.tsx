"use client";

import { useEffect } from "react";

import { recordRecentlyViewed } from "./use-recently-viewed";

type Props = {
  slug: string;
  name: string;
};

/** Records a PDP view into device-local recently viewed history. */
export function RecordRecentlyViewed({ slug, name }: Props): null {
  useEffect(() => {
    recordRecentlyViewed(slug, name);
  }, [slug, name]);
  return null;
}
