"use client";

import { useTranslations } from "next-intl";
import { useCallback, useEffect, useMemo, useState } from "react";

import { Button, Input, Select } from "../../../_lib/ui";
import {
  createDashboardClient,
  type Affiliate,
  type Promo,
  type TeamAddResult,
  type TeamList,
} from "../_lib/dashboard-client";

type EventOpsPanelProps = {
  eventId: string;
  getToken: () => string | null;
  locale: string;
};

export function EventOpsPanel({ eventId, getToken, locale }: EventOpsPanelProps) {
  const t = useTranslations("vendor.eventDashboard.ops");
  const client = useMemo(() => createDashboardClient(getToken), [getToken]);
  const [team, setTeam] = useState<TeamList | null>(null);
  const [promos, setPromos] = useState<Promo[]>([]);
  const [affiliates, setAffiliates] = useState<Affiliate[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [invitePhone, setInvitePhone] = useState("");
  const [inviteRole, setInviteRole] = useState<"manager" | "door">("door");
  const [lastToken, setLastToken] = useState<string | null>(null);
  const [promoCode, setPromoCode] = useState("");
  const [promoValue, setPromoValue] = useState("10");
  const [affiliateCode, setAffiliateCode] = useState("");
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    setError(null);
    try {
      const [nextTeam, nextPromos, nextAffiliates] = await Promise.all([
        client.getTeam(eventId),
        client.getPromos(eventId),
        client.getAffiliates(eventId),
      ]);
      setTeam(nextTeam);
      setPromos(nextPromos.items);
      setAffiliates(nextAffiliates.items);
    } catch {
      setError(t("loadFailed"));
    }
  }, [client, eventId, t]);

  useEffect(() => {
    void load();
  }, [load]);

  const onInvite = async () => {
    setBusy(true);
    setError(null);
    setLastToken(null);
    try {
      const result: TeamAddResult = await client.addTeamMember(eventId, {
        role: inviteRole,
        phone: invitePhone,
      });
      if (result.invite_token) {
        setLastToken(result.invite_token);
      }
      setInvitePhone("");
      await load();
    } catch {
      setError(t("inviteFailed"));
    } finally {
      setBusy(false);
    }
  };

  const onPromo = async () => {
    setBusy(true);
    setError(null);
    try {
      await client.createPromo(eventId, {
        code: promoCode,
        discount_kind: "percent",
        discount_value: Number.parseInt(promoValue, 10) || 0,
      });
      setPromoCode("");
      await load();
    } catch {
      setError(t("promoFailed"));
    } finally {
      setBusy(false);
    }
  };

  const onAffiliate = async () => {
    setBusy(true);
    setError(null);
    try {
      await client.createAffiliate(eventId, { code: affiliateCode });
      setAffiliateCode("");
      await load();
    } catch {
      setError(t("affiliateFailed"));
    } finally {
      setBusy(false);
    }
  };

  const acceptPath = `/${locale}/account/event-team/accept`;

  return (
    <section className="flex flex-col gap-4 rounded-lg border border-border bg-surface p-3 shadow-sm">
      <h2 className="text-sm font-semibold">{t("heading")}</h2>
      <p className="text-sm text-muted">{t("intro")}</p>
      {error ? (
        <p className="text-sm text-danger" role="alert">
          {error}
        </p>
      ) : null}

      <div className="flex flex-col gap-2">
        <h3 className="text-sm font-medium">{t("teamHeading")}</h3>
        <ul className="flex flex-col gap-1 text-sm">
          {(team?.members ?? []).map((member) => (
            <li key={member.id} className="flex items-center justify-between gap-2">
              <span>
                {member.role} · {member.user_id.slice(0, 8)}
              </span>
              {member.role !== "owner" ? (
                <button
                  type="button"
                  className="text-danger underline-offset-2 hover:underline"
                  onClick={() => {
                    void client.revokeTeamMember(eventId, member.id).then(() => load());
                  }}
                >
                  {t("revoke")}
                </button>
              ) : null}
            </li>
          ))}
          {(team?.invites ?? []).map((invite) => (
            <li key={invite.id} className="text-muted">
              {t("pendingInvite", { phone: invite.invitee_phone, role: invite.role })}
            </li>
          ))}
        </ul>
        <div className="flex flex-col gap-2 sm:flex-row">
          <Input
            value={invitePhone}
            onChange={(event) => setInvitePhone(event.target.value)}
            placeholder={t("phonePlaceholder")}
            aria-label={t("phonePlaceholder")}
          />
          <Select
            value={inviteRole}
            onChange={(event) => setInviteRole(event.target.value as "manager" | "door")}
            aria-label={t("roleLabel")}
          >
            <option value="door">{t("roleDoor")}</option>
            <option value="manager">{t("roleManager")}</option>
          </Select>
          <Button
            type="button"
            disabled={busy || !invitePhone.trim()}
            loading={busy}
            loadingLabel={t("inviteCta")}
            onClick={() => void onInvite()}
          >
            {t("inviteCta")}
          </Button>
        </div>
        {lastToken ? (
          <p className="break-all text-sm text-text">
            {t("shareToken", { token: lastToken, path: acceptPath })}
          </p>
        ) : null}
      </div>

      <div className="flex flex-col gap-2">
        <h3 className="text-sm font-medium">{t("promoHeading")}</h3>
        <ul className="text-sm">
          {promos.map((promo) => (
            <li key={promo.id}>
              {promo.code} ·{" "}
              {promo.discount_kind === "percent"
                ? `${promo.discount_value}%`
                : promo.discount_value}
            </li>
          ))}
        </ul>
        <div className="flex flex-col gap-2 sm:flex-row">
          <Input
            value={promoCode}
            onChange={(event) => setPromoCode(event.target.value)}
            placeholder={t("promoCodePlaceholder")}
            aria-label={t("promoCodePlaceholder")}
          />
          <Input
            value={promoValue}
            onChange={(event) => setPromoValue(event.target.value)}
            inputMode="numeric"
            placeholder={t("promoPercentPlaceholder")}
            aria-label={t("promoPercentPlaceholder")}
          />
          <Button
            type="button"
            disabled={busy || !promoCode.trim()}
            loading={busy}
            loadingLabel={t("promoCta")}
            onClick={() => void onPromo()}
          >
            {t("promoCta")}
          </Button>
        </div>
      </div>

      <div className="flex flex-col gap-2">
        <h3 className="text-sm font-medium">{t("affiliateHeading")}</h3>
        <p className="text-xs text-muted">{t("affiliateNote")}</p>
        <ul className="text-sm">
          {affiliates.map((row) => (
            <li key={row.id}>{row.code}</li>
          ))}
        </ul>
        <div className="flex flex-col gap-2 sm:flex-row">
          <Input
            value={affiliateCode}
            onChange={(event) => setAffiliateCode(event.target.value)}
            placeholder={t("affiliatePlaceholder")}
            aria-label={t("affiliatePlaceholder")}
          />
          <Button
            type="button"
            disabled={busy || !affiliateCode.trim()}
            loading={busy}
            loadingLabel={t("affiliateCta")}
            onClick={() => void onAffiliate()}
          >
            {t("affiliateCta")}
          </Button>
        </div>
      </div>
    </section>
  );
}
