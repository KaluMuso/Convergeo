"use client";

import { useCallback, useEffect, useRef, useState } from "react";

import { isSpeechRecognitionSupported, preferredEnglishLang } from "./speech-support";

import type { SpeechSession } from "./speech-session";

export type AskVoiceButtonLabels = {
  /** aria-label when idle, e.g. "Speak your question". */
  start: string;
  /** aria-label while listening, e.g. "Stop listening". */
  stop: string;
  /** Live-region text while listening. */
  listening: string;
  /** Live-region text on failure (mic blocked / no speech). */
  error: string;
};

export type AskVoiceButtonProps = {
  labels: AskVoiceButtonLabels;
  /** Interim + final transcripts; `isFinal` is true once the utterance ends. */
  onTranscript: (text: string, isFinal: boolean) => void;
  disabled?: boolean;
  className?: string;
};

type VoiceState = "idle" | "listening" | "error";

/**
 * Mic button for Ask Vergeo (Web Speech API, English only). Renders nothing when the
 * browser has no speech recognition, so unsupported browsers never see a dead control.
 * The recogniser module is `import()`-ed on first tap — zero cost until used, no new
 * dependency, and our code never uploads audio.
 *
 * Labels are passed in already-localised so the header / floating chat button can
 * mount this without an `ai` i18n provider.
 */
export function AskVoiceButton({
  labels,
  onTranscript,
  disabled = false,
  className,
}: AskVoiceButtonProps) {
  const [supported, setSupported] = useState(false);
  const [state, setState] = useState<VoiceState>("idle");
  const sessionRef = useRef<SpeechSession | null>(null);
  const onTranscriptRef = useRef(onTranscript);

  useEffect(() => {
    onTranscriptRef.current = onTranscript;
  }, [onTranscript]);

  useEffect(() => {
    // Detect after mount so SSR markup and first client render agree (hidden).
    setSupported(isSpeechRecognitionSupported());
    return () => {
      sessionRef.current?.abort();
      sessionRef.current = null;
    };
  }, []);

  const toggle = useCallback(async () => {
    if (state === "listening") {
      sessionRef.current?.stop();
      return;
    }
    setState("listening");
    let failed = false;
    const { startSpeechSession } = await import("./speech-session");
    sessionRef.current = startSpeechSession({
      lang: preferredEnglishLang(),
      onTranscript: (text, isFinal) => onTranscriptRef.current(text, isFinal),
      onError: (code) => {
        // "aborted" is our own cancel; "no-speech" just means silence.
        if (code !== "aborted") {
          failed = true;
          setState("error");
        }
      },
      onEnd: () => {
        sessionRef.current = null;
        if (!failed) {
          setState("idle");
        }
      },
    });
  }, [state]);

  if (!supported) {
    return null;
  }

  const listening = state === "listening";
  return (
    <span className="inline-flex items-center">
      <button
        type="button"
        data-testid="ask-voice-button"
        data-state={state}
        aria-label={listening ? labels.stop : labels.start}
        aria-pressed={listening}
        disabled={disabled}
        onClick={() => void toggle()}
        className={
          className ??
          "inline-flex min-h-11 min-w-11 items-center justify-center rounded-full border border-border bg-surface text-text hover:border-primary focus-visible:outline-none focus-visible:shadow-focusRing disabled:opacity-50 aria-pressed:border-primary aria-pressed:text-primary"
        }
      >
        <svg
          aria-hidden="true"
          viewBox="0 0 24 24"
          width="20"
          height="20"
          fill="none"
          stroke="currentColor"
          strokeWidth="2"
          strokeLinecap="round"
          strokeLinejoin="round"
        >
          <rect x="9" y="3" width="6" height="11" rx="3" />
          <path d="M5 11a7 7 0 0 0 14 0" />
          <path d="M12 18v3" />
        </svg>
      </button>
      <span role="status" aria-live="polite" className="sr-only" data-testid="ask-voice-status">
        {listening ? labels.listening : state === "error" ? labels.error : ""}
      </span>
    </span>
  );
}
