"use client";

import { PageHeader, type PageHeaderProps } from "@vergeo/ui/src/page-header";

/** Consistent page chrome for vendor routes (wraps design-system PageHeader). */
export function VendorRouteHeader(props: PageHeaderProps) {
  return <PageHeader {...props} />;
}
