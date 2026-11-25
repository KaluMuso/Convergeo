"use client";

import Link from "next/link";
import { useTranslations } from "next-intl";
import { useEffect, useState } from "react";

import { contactsApi, type Contact } from "../../../../../lib/social/contacts-api";

type ContactsListProps = { locale: string };

export function ContactsList({ locale }: ContactsListProps) {
  const t = useTranslations("social.contacts");
  const [items, setItems] = useState<Contact[]>([]);
  const [error, setError] = useState(false);

  useEffect(() => {
    void contactsApi
      .listContacts()
      .then((data) => setItems(data.items))
      .catch(() => setError(true));
  }, []);

  if (error) {
    return <p className="text-sm text-muted">{t("empty")}</p>;
  }

  if (!items.length) {
    return <p className="text-sm text-muted">{t("empty")}</p>;
  }

  return (
    <ul className="divide-y divide-border rounded border border-border">
      {items.map((c) => (
        <li key={c.user_id} className="flex flex-wrap items-center justify-between gap-2 px-4 py-3">
          <div>
            <p className="font-medium text-display-ink">
              {c.display_name ?? c.handle ?? c.user_id}
            </p>
            {c.handle ? <p className="text-sm text-muted">@{c.handle}</p> : null}
          </div>
          <div className="flex flex-wrap gap-2">
            {c.thread_id ? (
              <Link
                href={`/${locale}/account/people/chats/${c.thread_id}`}
                className="rounded border border-border px-3 py-1 text-xs font-medium"
              >
                {t("message")}
              </Link>
            ) : null}
            <Link
              href={`/${locale}/checkout?gift=1`}
              className="rounded border border-border px-3 py-1 text-xs font-medium"
            >
              {t("gift")}
            </Link>
          </div>
        </li>
      ))}
    </ul>
  );
}
