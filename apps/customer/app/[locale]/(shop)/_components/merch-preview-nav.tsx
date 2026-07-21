"use client";

import Link from "next/link";
import type { ComponentProps } from "react";
import { useSyncExternalStore } from "react";

const PREVIEW_PARAM = "merch_preview";

function readPreviewToken(): string | null {
  if (typeof window === "undefined") {
    return null;
  }
  return new URLSearchParams(window.location.search).get(PREVIEW_PARAM);
}

/** Append `?merch_preview=` when previewing draft merch across shop navigation. */
export function withMerchPreviewParam(href: string, token: string | null | undefined): string {
  if (!token || !href.startsWith("/")) {
    return href;
  }
  const hashIndex = href.indexOf("#");
  const path = hashIndex >= 0 ? href.slice(0, hashIndex) : href;
  const hash = hashIndex >= 0 ? href.slice(hashIndex) : "";
  const [pathname, search = ""] = path.split("?");
  const params = new URLSearchParams(search);
  params.set(PREVIEW_PARAM, token);
  const query = params.toString();
  return `${pathname}?${query}${hash}`;
}

/** Read the active merch preview token from the current URL (client components only). */
export function useMerchPreviewToken(): string | null {
  return useSyncExternalStore(
    () => () => {},
    readPreviewToken,
    () => null,
  );
}

type MerchPreviewLinkProps = ComponentProps<typeof Link>;

/** Internal shop link that preserves `?merch_preview=` while draft previewing. */
export function MerchPreviewLink({ href, ...props }: MerchPreviewLinkProps) {
  const previewToken = useMerchPreviewToken();
  const resolvedHref = typeof href === "string" ? withMerchPreviewParam(href, previewToken) : href;
  return <Link href={resolvedHref} {...props} />;
}
