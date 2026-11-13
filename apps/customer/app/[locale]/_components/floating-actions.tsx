"use client";

import { usePathname, useRouter } from "next/navigation";
import {
  useCallback,
  useEffect,
  useId,
  useRef,
  useState,
  type ReactNode,
} from "react";

export type FloatingActionsLabels = {
  ask: string;
  askTitle: string;
  askHint: string;
  askPlaceholder: string;
  send: string;
  voiceStart: string;
  voiceStop: string;
  listening: string;
  voiceUnsupported: string;
  close: string;
  showFooter: string;
  hideFooter: string;
};

type FloatingActionsProps = {
  locale: string;
  labels: FloatingActionsLabels;
  /** The site footer. Rendered inline on most pages; on home it is hidden and
   * opened as an overlay sheet so infinite scroll never collides with it. */
  footer: ReactNode;
};

/* Minimal Web Speech API typing (Chrome/Edge/Safari expose webkitSpeechRecognition). */
type SpeechRecognitionLike = {
  lang: string;
  interimResults: boolean;
  continuous: boolean;
  onresult:
    | ((event: {
        results: ArrayLike<ArrayLike<{ transcript: string }>>;
      }) => void)
    | null;
  onend: (() => void) | null;
  onerror: (() => void) | null;
  start: () => void;
  stop: () => void;
};
type SpeechRecognitionCtor = new () => SpeechRecognitionLike;

function getSpeechRecognition(): SpeechRecognitionCtor | null {
  if (typeof window === "undefined") {
    return null;
  }
  const w = window as unknown as {
    SpeechRecognition?: SpeechRecognitionCtor;
    webkitSpeechRecognition?: SpeechRecognitionCtor;
  };
  return w.SpeechRecognition ?? w.webkitSpeechRecognition ?? null;
}

const SPEECH_LANG: Record<string, string> = {
  en: "en-ZM",
  fr: "fr-FR",
  zh: "zh-CN",
};

/** Routes where a sticky mobile add-to-cart bar sits at the bottom. */
function hasStickyBuyBar(pathname: string): boolean {
  return /\/(p|l)\/[^/]+/.test(pathname);
}

export function isHomePath(pathname: string, locale: string): boolean {
  return pathname === `/${locale}` || pathname === `/${locale}/`;
}

/**
 * Bottom-right floating actions: Ask Vergeo (typed or dictated) and, on the
 * home feed, a toggle that opens the footer as an overlay sheet.
 */
export function FloatingActions({
  locale,
  labels,
  footer,
}: FloatingActionsProps) {
  const pathname = usePathname() ?? `/${locale}`;
  const router = useRouter();
  const home = isHomePath(pathname, locale);
  const raised = hasStickyBuyBar(pathname);

  const [askOpen, setAskOpen] = useState(false);
  const [footerOpen, setFooterOpen] = useState(false);
  const [query, setQuery] = useState("");
  const [listening, setListening] = useState(false);
  const [voiceSupported, setVoiceSupported] = useState(false);
  const recognitionRef = useRef<SpeechRecognitionLike | null>(null);
  const inputRef = useRef<HTMLInputElement>(null);
  const askTriggerRef = useRef<HTMLButtonElement>(null);
  const titleId = useId();
  const footerSheetId = useId();

  useEffect(() => {
    setVoiceSupported(getSpeechRecognition() !== null);
  }, []);

  // Close overlays on navigation.
  useEffect(() => {
    setAskOpen(false);
    setFooterOpen(false);
  }, [pathname]);

  useEffect(() => {
    if (askOpen) {
      inputRef.current?.focus();
    }
  }, [askOpen]);

  const stopListening = useCallback(() => {
    recognitionRef.current?.stop();
    recognitionRef.current = null;
    setListening(false);
  }, []);

  const closeAsk = useCallback(() => {
    stopListening();
    setAskOpen(false);
    askTriggerRef.current?.focus();
  }, [stopListening]);

  useEffect(() => {
    if (!askOpen && !footerOpen) {
      return;
    }
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        if (askOpen) {
          closeAsk();
        }
        setFooterOpen(false);
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [askOpen, footerOpen, closeAsk]);

  const startListening = () => {
    const Ctor = getSpeechRecognition();
    if (!Ctor) {
      return;
    }
    const recognition = new Ctor();
    recognition.lang = SPEECH_LANG[locale] ?? "en-ZM";
    recognition.interimResults = true;
    recognition.continuous = false;
    recognition.onresult = (event) => {
      let text = "";
      for (let i = 0; i < event.results.length; i += 1) {
        text += event.results[i]?.[0]?.transcript ?? "";
      }
      setQuery(text);
    };
    recognition.onend = () => setListening(false);
    recognition.onerror = () => setListening(false);
    recognitionRef.current = recognition;
    setListening(true);
    recognition.start();
  };

  const submit = () => {
    const q = query.trim();
    stopListening();
    setAskOpen(false);
    router.push(
      q ? `/${locale}/ask?q=${encodeURIComponent(q)}` : `/${locale}/ask`,
    );
  };

  const onAskPage = pathname.startsWith(`/${locale}/ask`);

  return (
    <>
      {home ? null : footer}

      <div
        className={`v-fab-stack ${raised ? "v-fab-stack--raised" : ""}`}
        data-testid="floating-actions"
      >
        {home ? (
          <button
            type="button"
            className="v-fab v-fab--small"
            aria-expanded={footerOpen}
            aria-controls={footerSheetId}
            aria-label={footerOpen ? labels.hideFooter : labels.showFooter}
            title={footerOpen ? labels.hideFooter : labels.showFooter}
            data-testid="fab-footer-toggle"
            onClick={() => setFooterOpen((open) => !open)}
          >
            <svg
              aria-hidden
              viewBox="0 0 24 24"
              width="18"
              height="18"
              fill="none"
              stroke="currentColor"
              strokeWidth="2"
              strokeLinecap="round"
            >
              {footerOpen ? (
                <path d="M6 9l6 6 6-6" />
              ) : (
                <path d="M4 7h16M4 12h16M4 17h10" />
              )}
            </svg>
          </button>
        ) : null}
        {onAskPage ? null : (
          <button
            ref={askTriggerRef}
            type="button"
            className="v-fab"
            aria-haspopup="dialog"
            aria-expanded={askOpen}
            aria-label={labels.ask}
            title={labels.ask}
            data-testid="fab-ask"
            onClick={() => (askOpen ? closeAsk() : setAskOpen(true))}
          >
            <svg
              aria-hidden
              viewBox="0 0 24 24"
              width="22"
              height="22"
              fill="none"
              stroke="currentColor"
              strokeWidth="1.9"
              strokeLinecap="round"
              strokeLinejoin="round"
            >
              <path d="M4 18.5V6.5A2.5 2.5 0 0 1 6.5 4h11A2.5 2.5 0 0 1 20 6.5v7a2.5 2.5 0 0 1-2.5 2.5H8.5L4 18.5Z" />
              <path
                d="M12 7.2l.8 2 2 .8-2 .8-.8 2-.8-2-2-.8 2-.8.8-2Z"
                fill="currentColor"
                stroke="none"
              />
            </svg>
          </button>
        )}
      </div>

      {askOpen ? (
        <div
          role="dialog"
          aria-modal="false"
          aria-labelledby={titleId}
          className={`v-fab-panel ${raised ? "v-fab-stack--raised" : ""}`}
          data-testid="fab-ask-panel"
        >
          <div className="flex items-start justify-between gap-3">
            <div>
              <h2
                id={titleId}
                className="m-0 font-display text-lg font-bold text-text"
              >
                {labels.askTitle}
              </h2>
              <p className="m-0 mt-1 text-sm text-text-2">{labels.askHint}</p>
            </div>
            <button
              type="button"
              onClick={closeAsk}
              aria-label={labels.close}
              className="inline-flex min-h-11 min-w-11 items-center justify-center rounded text-text-3 hover:bg-bg-2 hover:text-text"
            >
              <svg
                aria-hidden
                viewBox="0 0 24 24"
                width="16"
                height="16"
                fill="none"
                stroke="currentColor"
                strokeWidth="2.2"
                strokeLinecap="round"
              >
                <path d="M6 6l12 12M18 6 6 18" />
              </svg>
            </button>
          </div>
          <form
            className="mt-3 flex items-center gap-2"
            onSubmit={(event) => {
              event.preventDefault();
              submit();
            }}
          >
            <label className="sr-only" htmlFor={`${titleId}-input`}>
              {labels.askTitle}
            </label>
            <input
              id={`${titleId}-input`}
              ref={inputRef}
              value={query}
              onChange={(event) => setQuery(event.target.value)}
              placeholder={listening ? labels.listening : labels.askPlaceholder}
              className="h-11 min-w-0 flex-1 rounded-pill border border-border bg-bg px-4 text-body text-text placeholder:text-text-3 focus:border-primary focus:outline-none"
              data-testid="fab-ask-input"
            />
            {voiceSupported ? (
              <button
                type="button"
                onClick={listening ? stopListening : startListening}
                aria-pressed={listening}
                aria-label={listening ? labels.voiceStop : labels.voiceStart}
                title={listening ? labels.voiceStop : labels.voiceStart}
                data-testid="fab-ask-voice"
                className={`inline-flex h-11 w-11 shrink-0 items-center justify-center rounded-full border transition-colors ${
                  listening
                    ? "border-accent bg-accent text-[var(--primary-btn-fg)]"
                    : "border-border bg-surface text-text-2 hover:text-primary"
                }`}
              >
                <svg
                  aria-hidden
                  viewBox="0 0 24 24"
                  width="18"
                  height="18"
                  fill="none"
                  stroke="currentColor"
                  strokeWidth="2"
                  strokeLinecap="round"
                  strokeLinejoin="round"
                >
                  <rect x="9" y="3" width="6" height="11" rx="3" />
                  <path d="M5 11a7 7 0 0 0 14 0M12 18v3" />
                </svg>
              </button>
            ) : null}
            <button
              type="submit"
              className="inline-flex h-11 shrink-0 items-center rounded-pill bg-primary px-4 text-sm font-semibold text-[var(--primary-btn-fg)] hover:bg-[var(--primary-btn-hover)]"
            >
              {labels.send}
            </button>
          </form>
          {voiceSupported ? null : (
            <p
              className="m-0 mt-2 text-sm text-text-3"
              data-testid="fab-voice-unsupported"
            >
              {labels.voiceUnsupported}
            </p>
          )}
          <p aria-live="polite" className="sr-only">
            {listening ? labels.listening : ""}
          </p>
        </div>
      ) : null}

      {home ? (
        <div
          id={footerSheetId}
          className="v-footer-sheet"
          data-open={footerOpen ? "true" : "false"}
          hidden={!footerOpen}
          data-testid="footer-sheet"
        >
          {footer}
        </div>
      ) : null}
    </>
  );
}
