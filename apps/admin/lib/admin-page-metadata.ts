import type { Metadata } from "next";

import { getAdminTranslator } from "./admin-translator";

/** Document title from `admin.nav.*` (matches sidebar labels). */
export async function adminNavPageMetadata(
  locale: string,
  navKey: string,
): Promise<Metadata> {
  const t = await getAdminTranslator(locale, "admin.nav");
  return { title: t(navKey) };
}

/** Document title from any loaded admin namespace key (e.g. `admin.kyc.title`). */
export async function adminSectionPageMetadata(
  locale: string,
  namespace: string,
  titleKey = "title",
): Promise<Metadata> {
  const t = await getAdminTranslator(locale, namespace);
  return { title: t(titleKey) };
}