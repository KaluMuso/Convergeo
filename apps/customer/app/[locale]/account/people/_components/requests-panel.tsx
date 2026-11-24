"use client";

import { useTranslations } from "next-intl";
import { useEffect, useState } from "react";

import { contactsApi, type ContactRequest } from "../../../../../lib/social/contacts-api";

export function RequestsPanel() {
  const t = useTranslations("social.requests");
  const [incoming, setIncoming] = useState<ContactRequest[]>([]);
  const [outgoing, setOutgoing] = useState<ContactRequest[]>([]);

  const reload = () => {
    void contactsApi.listRequests("in").then((data) => setIncoming(data.items));
    void contactsApi.listRequests("out").then((data) => setOutgoing(data.items));
  };

  useEffect(() => {
    reload();
  }, []);

  return (
    <div className="space-y-8">
      <section>
        <h2 className="mb-3 font-semibold">{t("incoming")}</h2>
        {incoming.length === 0 ? (
          <p className="text-sm text-muted">{t("empty")}</p>
        ) : (
          <RequestRows items={incoming} onChange={reload} t={t} incoming />
        )}
      </section>
      <section>
        <h2 className="mb-3 font-semibold">{t("outgoing")}</h2>
        {outgoing.length === 0 ? (
          <p className="text-sm text-muted">{t("empty")}</p>
        ) : (
          <RequestRows items={outgoing} onChange={reload} t={t} />
        )}
      </section>
    </div>
  );
}

function RequestRows({
  items,
  onChange,
  t,
  incoming = false,
}: {
  items: ContactRequest[];
  onChange: () => void;
  t: ReturnType<typeof useTranslations>;
  incoming?: boolean;
}) {
  return (
    <ul className="space-y-3">
      {items.map((r) => (
        <li key={r.id} className="rounded border border-border p-3 text-sm">
          <p className="font-medium">{r.note ?? r.id}</p>
          <p className="text-muted">
            {r.outgoing ? t("pending") : r.status === "pending" ? t("pending") : r.status}
          </p>
          {incoming ? (
            <div className="mt-2 flex flex-wrap gap-2">
              <button
                type="button"
                className="rounded bg-primary px-3 py-1 text-xs text-surface"
                onClick={() => void contactsApi.acceptRequest(r.id).then(onChange)}
              >
                {t("accept")}
              </button>
              <button
                type="button"
                className="rounded border border-border px-3 py-1 text-xs"
                onClick={() => void contactsApi.ignoreRequest(r.id).then(onChange)}
              >
                {t("ignore")}
              </button>
              <button
                type="button"
                className="rounded border border-border px-3 py-1 text-xs"
                onClick={() => void contactsApi.blockUser(r.from_user).then(onChange)}
              >
                {t("block")}
              </button>
            </div>
          ) : (
            <p className="mt-1 text-xs text-muted" data-testid="outgoing-status">
              {t("pending")}
            </p>
          )}
        </li>
      ))}
    </ul>
  );
}
