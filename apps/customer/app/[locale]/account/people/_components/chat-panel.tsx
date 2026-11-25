"use client";

import { useTranslations } from "next-intl";
import { useCallback, useEffect, useState } from "react";

import { contactsApi, type ChatMessage } from "../../../../../lib/social/contacts-api";

type ChatPanelProps = { threadId: string; selfId?: string };

export function ChatPanel({ threadId }: ChatPanelProps) {
  const t = useTranslations("social.chat");
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [draft, setDraft] = useState("");
  const [sending, setSending] = useState(false);

  const load = useCallback(() => {
    void contactsApi
      .listMessages(threadId)
      .then((data) => setMessages([...data.items].reverse()))
      .catch(() => setMessages([]));
  }, [threadId]);

  useEffect(() => {
    load();
    const timer = window.setInterval(load, 15_000);
    return () => window.clearInterval(timer);
  }, [load]);

  const send = async () => {
    if (!draft.trim()) return;
    setSending(true);
    try {
      await contactsApi.sendMessage(threadId, draft.trim());
      setDraft("");
      load();
    } finally {
      setSending(false);
    }
  };

  return (
    <div className="mx-auto flex max-w-lg flex-col gap-4">
      <ul className="min-h-[240px] space-y-2 rounded border border-border p-3">
        {messages.map((m) => (
          <li key={m.id} className="text-sm">
            <span className="text-muted">{new Date(m.created_at).toLocaleTimeString()}</span>
            <p>{m.body}</p>
          </li>
        ))}
      </ul>
      <div className="flex gap-2">
        <input
          className="flex-1 rounded border border-border px-3 py-2 text-sm"
          placeholder={t("placeholder")}
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
        />
        <button
          type="button"
          disabled={sending}
          className="min-h-11 rounded bg-primary px-4 text-sm font-medium text-surface"
          onClick={() => void send()}
        >
          {t("send")}
        </button>
      </div>
      <p className="sr-only">{t("polling")}</p>
    </div>
  );
}
