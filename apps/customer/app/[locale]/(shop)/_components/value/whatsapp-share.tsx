"use client";

import { ShareLinkButton } from "../../../_components/share-link-button";

export type WhatsAppShareProps = {
  title: string;
  line: string;
  url: string;
  label: string;
  className?: string;
};

export function WhatsAppShare({ title, line, url, label, className }: WhatsAppShareProps) {
  return (
    <ShareLinkButton label={label} title={title} text={line} url={url} className={className} />
  );
}
