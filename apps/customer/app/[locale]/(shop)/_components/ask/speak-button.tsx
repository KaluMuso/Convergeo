"use client";

import { useCallback, useEffect, useRef, useState } from "react";

import { isSpeechSynthesisSupported, pickVoice, utteranceLang } from "./speech-synthesis";

export type AskSpeakButtonLabels = {
  /** aria-label when idle, e.g. "Read the answer aloud". */
  speak: string;
  /** aria-label while speaking, e.g. "Stop reading". */
  stop: string;
};

export type AskSpeakButtonProps = {
  text: string;
  locale: string;
  labels: AskSpeakButtonLabels;
};

/**
 * Speaker button that reads an Ask answer aloud with `speechSynthesis`. Renders nothing
 * when the browser has no speech synthesis. Tapping again stops it; speech is cancelled
 * when the answer changes and when the component unmounts.
 */
export function AskSpeakButton({ text, locale, labels }: AskSpeakButtonProps) {
  const [supported, setSupported] = useState(false);
  const [speaking, setSpeaking] = useState(false);
  const activeRef = useRef(false);

  useEffect(() => {
    // Detect after mount so SSR markup and the first client render agree (hidden).
    setSupported(isSpeechSynthesisSupported());
  }, []);

  const stop = useCallback(() => {
    if (activeRef.current && isSpeechSynthesisSupported()) {
      window.speechSynthesis.cancel();
    }
    activeRef.current = false;
    setSpeaking(false);
  }, []);

  // New answer text or unmount: never keep talking over the next answer.
  useEffect(() => stop, [text, stop]);

  const toggle = () => {
    if (speaking) {
      stop();
      return;
    }
    const synth = window.speechSynthesis;
    synth.cancel();
    const utterance = new window.SpeechSynthesisUtterance(text);
    const voice = pickVoice(synth.getVoices(), locale);
    if (voice) {
      utterance.voice = voice;
    }
    utterance.lang = utteranceLang(voice, locale);
    const finish = () => {
      activeRef.current = false;
      setSpeaking(false);
    };
    utterance.onend = finish;
    utterance.onerror = finish;
    activeRef.current = true;
    setSpeaking(true);
    synth.speak(utterance);
  };

  if (!supported) {
    return null;
  }

  return (
    <button
      type="button"
      data-testid="ask-speak-button"
      data-state={speaking ? "speaking" : "idle"}
      aria-label={speaking ? labels.stop : labels.speak}
      aria-pressed={speaking}
      onClick={toggle}
      className="inline-flex min-h-11 min-w-11 items-center justify-center rounded-full border border-border bg-surface text-text hover:border-primary focus-visible:outline-none focus-visible:shadow-focusRing aria-pressed:border-primary aria-pressed:text-primary"
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
        <path d="M11 5 6 9H3v6h3l5 4z" />
        <path d="M15.5 8.5a5 5 0 0 1 0 7" />
        <path d="M18.5 5.5a9 9 0 0 1 0 13" />
      </svg>
    </button>
  );
}
