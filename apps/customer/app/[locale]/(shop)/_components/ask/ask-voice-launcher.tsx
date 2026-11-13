"use client";

import { useRouter } from "next/navigation";
import { useCallback } from "react";

import { AskVoiceButton, type AskVoiceButtonLabels } from "./voice-button";

export type AskVoiceLauncherProps = {
  locale: string;
  labels: AskVoiceButtonLabels;
  className?: string;
};

/**
 * Integration point for the header / floating chat button (owned by the storefront
 * shell): a self-contained mic that, once the user finishes speaking, opens
 * `/{locale}/ask?q=<transcript>` where the Ask thread auto-submits it.
 *
 * Renders nothing on browsers without the Web Speech API. Labels are pre-localised
 * by the host (keys: `ai.ask.voiceStart|voiceStop|voiceListening|voiceError`).
 *
 * Usage (FAB / header):
 *   <AskVoiceLauncher locale={locale} labels={{ start, stop, listening, error }} />
 */
export function AskVoiceLauncher({ locale, labels, className }: AskVoiceLauncherProps) {
  const router = useRouter();

  const handleTranscript = useCallback(
    (text: string, isFinal: boolean) => {
      if (!isFinal || !text.trim()) {
        return;
      }
      router.push(`/${locale}/ask?q=${encodeURIComponent(text.trim())}`);
    },
    [locale, router],
  );

  return <AskVoiceButton labels={labels} onTranscript={handleTranscript} className={className} />;
}
