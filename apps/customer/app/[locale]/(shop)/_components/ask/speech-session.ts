import { getSpeechRecognitionCtor, type SpeechRecognitionLike } from "./speech-support";

export type SpeechSessionOptions = {
  lang: "en-GB" | "en-US";
  /** Called with the latest (interim or final) transcript. */
  onTranscript: (text: string, isFinal: boolean) => void;
  onError: (code: string) => void;
  onEnd: () => void;
};

export type SpeechSession = {
  stop: () => void;
  abort: () => void;
};

/**
 * Start one single-utterance recognition session. Lazy-loaded from the mic button,
 * so none of this ships until a user actually taps it.
 */
export function startSpeechSession(options: SpeechSessionOptions): SpeechSession | null {
  const Ctor = getSpeechRecognitionCtor();
  if (!Ctor) {
    options.onError("unsupported");
    options.onEnd();
    return null;
  }

  let recognition: SpeechRecognitionLike;
  try {
    recognition = new Ctor();
  } catch {
    options.onError("unsupported");
    options.onEnd();
    return null;
  }

  recognition.lang = options.lang;
  recognition.continuous = false;
  recognition.interimResults = true;
  recognition.maxAlternatives = 1;

  recognition.onresult = (event) => {
    let transcript = "";
    let isFinal = false;
    for (let index = 0; index < event.results.length; index += 1) {
      const result = event.results[index];
      if (!result || result.length === 0) {
        continue;
      }
      transcript += result[0]?.transcript ?? "";
      isFinal = isFinal || result.isFinal;
    }
    const cleaned = transcript.replace(/\s+/g, " ").trim().slice(0, 500);
    if (cleaned) {
      options.onTranscript(cleaned, isFinal);
    }
  };
  recognition.onerror = (event) => {
    options.onError(event?.error ?? "unknown");
  };
  recognition.onend = () => {
    options.onEnd();
  };

  try {
    recognition.start();
  } catch {
    options.onError("start_failed");
    options.onEnd();
    return null;
  }

  return {
    stop: () => recognition.stop(),
    abort: () => recognition.abort(),
  };
}
