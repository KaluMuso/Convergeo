"use client";

import { ShareLinkButton } from "../../../_components/share-link-button";

export type WhatsAppShareProps = {
  /** Native share title (usually the listing name). */
  title: string;
  /** Body line shown in share text, e.g. "Samsung A15, from K2,450 on Vergeo5". */
  line: string;
  url: string;
  label: string;
  className?: string;
};

/** Thin wrapper over ShareLinkButton with a precomposed WhatsApp-friendly line. */
export function WhatsAppShare({ title, line, url, label, className }: WhatsAppShareProps) {
  return (
    <ShareLinkButton label={label} title={title} text={line} url={url} className={className} />
  );
}
