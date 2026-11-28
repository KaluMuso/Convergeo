/**
 * Browser text-to-speech (Web Speech `speechSynthesis`) for Ask answers. Free, no server
 * key, nothing uploaded by our code. Feature-detected so unsupported browsers never see
 * a dead control.
 */

/** Page locale -> preferred voice language. bem/nya have no voices; read them in English. */
const VOICE_LANG: Record<string, string> = {
  en: "en",
  fr: "fr",
  zh: "zh",
  bem: "en",
  nya: "en",
};

export function isSpeechSynthesisSupported(): boolean {
  return (
    typeof window !== "undefined" &&
    "speechSynthesis" in window &&
    typeof window.SpeechSynthesisUtterance === "function"
  );
}

function langPrefix(lang: string): string {
  return lang.toLowerCase().split(/[-_]/)[0] ?? "";
}

/** Voice for the page locale, falling back to any English voice, else `null` (browser default). */
export function pickVoice(
  voices: readonly SpeechSynthesisVoice[],
  locale: string,
): SpeechSynthesisVoice | null {
  const wanted = VOICE_LANG[locale] ?? "en";
  const exact = voices.find((voice) => langPrefix(voice.lang) === wanted);
  if (exact) {
    return exact;
  }
  return voices.find((voice) => langPrefix(voice.lang) === "en") ?? null;
}

export function utteranceLang(voice: SpeechSynthesisVoice | null, locale: string): string {
  if (voice) {
    return voice.lang;
  }
  const wanted = VOICE_LANG[locale] ?? "en";
  if (wanted === "fr") {
    return "fr-FR";
  }
  return wanted === "zh" ? "zh-CN" : "en-GB";
}
