"use client";

import { useTranslations } from "next-intl";
import { useEffect, useRef, useState } from "react";

import {
  type AdminIdentity,
  type AdminRoleKind,
  adminDisplayName,
} from "../../../lib/admin-identity";

import { SignOutButton } from "./sign-out-button";

type AdminAccountMenuProps = {
  locale: string;
  identity: AdminIdentity;
  roleKind: AdminRoleKind | null;
};

function initialsOf(label: string): string {
  const parts = label.split(/[\s._-]+/).filter(Boolean);
  const first = parts[0] ?? label;
  const second = parts[1];
  return (second ? first.charAt(0) + second.charAt(0) : first.slice(0, 2)).toUpperCase();
}

/** Top-bar account chip: who is signed in, their role, and a small menu with sign out. */
export function AdminAccountMenu({ locale, identity, roleKind }: AdminAccountMenuProps) {
  const t = useTranslations("admin.shell.account");
  const tShell = useTranslations("admin.shell");
  const rootRef = useRef<HTMLDivElement>(null);
  const buttonRef = useRef<HTMLButtonElement>(null);
  const [open, setOpen] = useState(false);

  useEffect(() => {
    if (!open) {
      return;
    }
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        setOpen(false);
        buttonRef.current?.focus();
      }
    };
    const onPointerDown = (event: MouseEvent) => {
      if (rootRef.current && !rootRef.current.contains(event.target as Node)) {
        setOpen(false);
      }
    };
    window.addEventListener("keydown", onKeyDown);
    document.addEventListener("mousedown", onPointerDown);
    return () => {
      window.removeEventListener("keydown", onKeyDown);
      document.removeEventListener("mousedown", onPointerDown);
    };
  }, [open]);

  const displayName = adminDisplayName(identity);
  const roleLabel = roleKind ? t(`roles.${roleKind}`) : null;
  const triggerLabel = displayName ?? t("unknownUser");

  return (
    <div ref={rootRef} className="relative" data-testid="admin-account">
      <button
        ref={buttonRef}
        type="button"
        className="inline-flex min-h-11 max-w-[14rem] items-center gap-2 rounded-md border border-panel-muted/40 px-2 text-left text-panel-text hover:border-panel-text"
        aria-haspopup="true"
        aria-expanded={open}
        aria-label={t("menuLabel")}
        onClick={() => setOpen((value) => !value)}
      >
        <span
          aria-hidden="true"
          className="inline-flex size-7 shrink-0 items-center justify-center rounded-full bg-panel-text/15 text-xs font-semibold"
        >
          {initialsOf(triggerLabel)}
        </span>
        <span className="hidden min-w-0 leading-tight sm:block">
          <span className="block truncate text-sm font-medium" data-testid="admin-account-name">
            {triggerLabel}
          </span>
          {roleLabel ? (
            <span
              className="block truncate text-xs text-panel-muted"
              data-testid="admin-account-role"
            >
              {roleLabel}
            </span>
          ) : null}
        </span>
      </button>
      {open ? (
        <div className="absolute right-0 top-full z-50 mt-1 w-64 space-y-2 rounded-md border border-border bg-surface p-3 text-text shadow-lg">
          <div className="space-y-0.5">
            <p className="truncate text-sm font-semibold">{triggerLabel}</p>
            {identity.email ? (
              <p className="truncate text-xs text-muted" data-testid="admin-account-email">
                {identity.email}
              </p>
            ) : null}
            {roleLabel ? (
              <p className="text-xs text-muted">{t("roleLine", { role: roleLabel })}</p>
            ) : null}
          </div>
          <SignOutButton
            locale={locale}
            label={tShell("signOut")}
            className="inline-flex min-h-11 w-full items-center justify-center rounded-md border border-border px-3 text-sm font-medium text-text disabled:opacity-60"
          />
        </div>
      ) : null}
    </div>
  );
}
