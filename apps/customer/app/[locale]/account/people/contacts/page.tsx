import { loadNamespace, LOCALES, type Locale } from "@vergeo/i18n";
import { createTranslator, type AbstractIntlMessages } from "next-intl";
import { setRequestLocale } from "next-intl/server";

import { ContactsList } from "../_components/contacts-list";
import { PeopleSubnav } from "../_components/people-subnav";

type PageProps = { params: Promise<{ locale: string }> };

export default async function PeopleContactsPage({ params }: PageProps) {
  const { locale } = await params;
  if (!LOCALES.includes(locale as Locale)) return null;
  setRequestLocale(locale);
  const social = await loadNamespace(locale as Locale, "social");
  const t = createTranslator({
    locale,
    messages: { social } as AbstractIntlMessages,
    namespace: "social",
  });
  return (
    <>
      <h2 className="mb-4 font-display text-h2 text-display-ink">{t("contacts.title")}</h2>
      <PeopleSubnav locale={locale} />
      <ContactsList locale={locale} />
    </>
  );
}
