"use client";

import { QrCode } from "@vergeo/ui/src/qr";
import { useTranslations } from "next-intl";
import { useCallback, useEffect, useMemo, useState } from "react";

import { contactsApi, type DiscoverMatch } from "../../../../../lib/social/contacts-api";
import {
  hashContactPhone,
  supportsContactPicker,
  waMeInviteLink,
  waMeShareLink,
} from "../../../../../lib/social/phone";

type PickedContact = { name: string; tel: string; hash: string | null };

type AddPeoplePanelProps = { locale: string; siteOrigin: string };

export function AddPeoplePanel({ locale, siteOrigin }: AddPeoplePanelProps) {
  const t = useTranslations("social.add");
  const [handle, setHandle] = useState("");
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [qr, setQr] = useState<{ handle: string; payload: string } | null>(null);
  const [matches, setMatches] = useState<DiscoverMatch[]>([]);
  const [unmatched, setUnmatched] = useState<PickedContact[]>([]);
  const [discoveryEnabled, setDiscoveryEnabled] = useState(false);
  const [pepperOk, setPepperOk] = useState(false);
  const inviteText = useMemo(
    () => `Join me on Convergeo: ${siteOrigin}/${locale}/account/people/add`,
    [locale, siteOrigin],
  );

  useEffect(() => {
    void contactsApi
      .getPhoneDiscovery()
      .then((state) => {
        setDiscoveryEnabled(state.enabled);
        setPepperOk(state.pepper_configured);
      })
      .catch(() => {
        setPepperOk(false);
      });
    void contactsApi
      .getQr()
      .then((data) => setQr({ handle: data.handle, payload: data.payload }))
      .catch(() => setQr(null));
  }, []);

  const onSendHandle = useCallback(async () => {
    setBusy(true);
    setMessage(null);
    try {
      await contactsApi.sendRequest(handle);
      setMessage("sent");
      setHandle("");
    } catch {
      setMessage("error");
    } finally {
      setBusy(false);
    }
  }, [handle]);

  const pickContacts = useCallback(async () => {
    const nav = navigator as Navigator & {
      contacts?: {
        select: (
          props: string[],
          opts: { multiple: boolean },
        ) => Promise<{ name?: string[]; tel?: string[] }[]>;
      };
    };
    if (!nav.contacts?.select) return;
    setBusy(true);
    try {
      const picked = await nav.contacts.select(["name", "tel"], { multiple: true });
      const hashes: string[] = [];
      const unmatchedLocal: PickedContact[] = [];
      for (const row of picked) {
        const name = row.name?.[0] ?? "";
        const tel = row.tel?.[0] ?? "";
        if (!tel) continue;
        const hash = await hashContactPhone(tel);
        if (hash) hashes.push(hash);
        unmatchedLocal.push({ name, tel, hash });
      }
      const result = await contactsApi.discoverHashes(hashes);
      setMatches(result.items);
      setUnmatched(
        result.items.length < unmatchedLocal.length
          ? unmatchedLocal.slice(result.items.length)
          : [],
      );
    } finally {
      setBusy(false);
    }
  }, []);

  const shareLink = useCallback(async () => {
    const shareUrl = qr
      ? `${siteOrigin}/${locale}/u/${qr.handle}`
      : `${siteOrigin}/${locale}/account/people/add`;
    if (typeof navigator.share === "function") {
      try {
        await navigator.share({ title: "Convergeo", url: shareUrl, text: inviteText });
        return;
      } catch {
        /* fall through */
      }
    }
    try {
      await navigator.clipboard.writeText(shareUrl);
      setMessage("copied");
    } catch {
      setMessage("error");
    }
  }, [inviteText, locale, qr, siteOrigin]);

  return (
    <div className="mx-auto max-w-lg space-y-8">
      <section className="space-y-3">
        <h2 className="text-lg font-semibold text-display-ink">{t("title")}</h2>
        <label className="block text-sm font-medium" htmlFor="people-handle">
          {t("handleLabel")}
        </label>
        <input
          id="people-handle"
          value={handle}
          onChange={(e) => setHandle(e.target.value)}
          placeholder={t("handlePlaceholder")}
          className="w-full rounded border border-border px-3 py-2 text-sm"
        />
        <button
          type="button"
          disabled={busy || !handle.trim()}
          className="min-h-11 rounded bg-primary px-4 text-sm font-medium text-surface disabled:opacity-50"
          onClick={() => void onSendHandle()}
        >
          {t("sendRequest")}
        </button>
      </section>

      {qr ? (
        <section className="space-y-3 rounded border border-border p-4">
          <h3 className="font-medium">{t("myQrTitle")}</h3>
          <p className="text-sm text-muted">@{qr.handle}</p>
          <QrCode value={qr.payload} title={t("scanTitle")} size={180} />
        </section>
      ) : null}

      <section className="space-y-3 rounded border border-border p-4">
        <h3 className="font-medium">{t("contactsTitle")}</h3>
        <p className="text-sm text-muted">{t("contactsExplainer")}</p>
        {supportsContactPicker() ? (
          <button
            type="button"
            className="min-h-11 rounded border border-border px-4 text-sm font-medium"
            disabled={busy || !pepperOk}
            data-testid="contact-picker-button"
            onClick={() => void pickContacts()}
          >
            {t("pickContacts")}
          </button>
        ) : (
          <div className="flex flex-col gap-2" data-testid="share-fallback">
            <button
              type="button"
              className="min-h-11 rounded border border-border px-4 text-sm font-medium"
              onClick={() => void shareLink()}
            >
              {t("shareLink")}
            </button>
            <a
              className="inline-flex min-h-11 items-center justify-center rounded border border-border px-4 text-sm font-medium"
              href={waMeShareLink(inviteText)}
              target="_blank"
              rel="noopener noreferrer"
            >
              {t("inviteWhatsApp")}
            </a>
          </div>
        )}
        <ul className="space-y-2">
          {matches.map((m) => (
            <li key={m.user_id} className="flex items-center justify-between gap-2 text-sm">
              <span>
                {m.display_name ?? m.handle ?? m.user_id}
                {m.handle ? <span className="text-muted"> @{m.handle}</span> : null}
              </span>
              <button
                type="button"
                className="rounded bg-primary px-3 py-1 text-xs font-medium text-surface"
                onClick={() => m.handle && void contactsApi.sendRequest(m.handle)}
              >
                {t("addMatch")}
              </button>
            </li>
          ))}
          {unmatched.map((c) => (
            <li
              key={`${c.name}-${c.tel}`}
              className="flex items-center justify-between gap-2 text-sm"
            >
              <span>
                {c.name || c.tel} <span className="text-muted">({t("notOnApp")})</span>
              </span>
              <a
                className="rounded border border-border px-3 py-1 text-xs font-medium"
                href={waMeInviteLink(
                  c.tel.startsWith("+") ? c.tel : `+${c.tel.replace(/\D/g, "")}`,
                  inviteText,
                )}
                target="_blank"
                rel="noopener noreferrer"
              >
                {t("inviteContact")}
              </a>
            </li>
          ))}
        </ul>
      </section>

      {pepperOk ? (
        <section className="space-y-2">
          <label className="flex items-start gap-3 text-sm">
            <input
              type="checkbox"
              checked={discoveryEnabled}
              onChange={(e) => {
                const next = e.target.checked;
                setDiscoveryEnabled(next);
                void contactsApi.setPhoneDiscovery(next).catch(() => setDiscoveryEnabled(!next));
              }}
            />
            <span>
              <span className="font-medium">{t("phoneDiscoveryLabel")}</span>
              <span className="mt-1 block text-muted">{t("phoneDiscoveryHelp")}</span>
            </span>
          </label>
        </section>
      ) : null}

      {message ? <p className="text-sm text-muted">{message}</p> : null}
    </div>
  );
}
