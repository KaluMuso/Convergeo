/**
 * Web Speech API feature detection (tiny, sync — safe to ship in the first load).
 * The recognition session itself lives in `speech-session.ts` and is only
 * `import()`-ed when the user taps the mic. No audio is uploaded by our code; the
 * browser's own recogniser handles it. English only (en-GB / en-US).
 */

export type SpeechRecognitionAlternativeLike = { transcript: string };
export type SpeechRecognitionResultLike = {
  isFinal: boolean;
  length: number;
  [index: number]: SpeechRecognitionAlternativeLike;
};
export type SpeechRecognitionEventLike = {
  resultIndex: number;
  results: { length: number; [index: number]: SpeechRecognitionResultLike };
};

export type SpeechRecognitionLike = {
  lang: string;
  continuous: boolean;
  interimResults: boolean;
  maxAlternatives: number;
  onresult: ((event: SpeechRecognitionEventLike) => void) | null;
  onerror: ((event: { error?: string }) => void) | null;
  onend: (() => void) | null;
  start: () => void;
  stop: () => void;
  abort: () => void;
};

export type SpeechRecognitionCtor = new () => SpeechRecognitionLike;

type SpeechWindow = Window & {
  SpeechRecognition?: SpeechRecognitionCtor;
  webkitSpeechRecognition?: SpeechRecognitionCtor;
};

export function getSpeechRecognitionCtor(): SpeechRecognitionCtor | null {
  if (typeof window === "undefined") {
    return null;
  }
  const speechWindow = window as SpeechWindow;
  return speechWindow.SpeechRecognition ?? speechWindow.webkitSpeechRecognition ?? null;
}

export function isSpeechRecognitionSupported(): boolean {
  return getSpeechRecognitionCtor() !== null;
}

/** English only: en-GB (Zambian default) unless the browser says en-US. */
export function preferredEnglishLang(): "en-GB" | "en-US" {
  if (typeof navigator === "undefined") {
    return "en-GB";
  }
  const languages = [navigator.language, ...(navigator.languages ?? [])].filter(Boolean);
  return languages.some((lang) => lang.toLowerCase() === "en-us") ? "en-US" : "en-GB";
}
