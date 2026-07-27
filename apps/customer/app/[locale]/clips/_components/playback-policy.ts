/**
 * M17-P04 — the rules that decide whether a single byte of video is fetched.
 *
 * This module is pure and has no React in it, because the decision it encodes is
 * the pebble: on a Zambian mobile bundle, an autoplay you did not ask for is
 * money out of someone's pocket. Keeping it pure means it is testable without a
 * DOM and impossible to accidentally couple to render order.
 *
 * The rules (D-V1, D-V2, D-V6):
 *
 * 1. **Poster-first, always.** Video bytes are fetched on an explicit tap.
 * 2. **Data saver is ON by default** and remembered. Saver ⇒ 480p ceiling, no
 *    preload, no autoplay.
 * 3. **Zero autoplay on cellular, no exceptions.** The only autoplay case is
 *    Wi-Fi AND saver off AND reduced-motion not requested — and then only the
 *    in-view clip, muted.
 * 4. **An unknown connection is treated as cellular.** Most Zambian visitors are
 *    on mobile data, and the Network Information API is not available in Safari
 *    at all — so "we don't know" must fail toward the bundle, not away from it.
 */

export type ConnectionKind = "wifi" | "cellular" | "unknown";

/** The subset of the Network Information API we rely on. */
type NetworkInformationLike = {
  type?: string;
  effectiveType?: string;
  saveData?: boolean;
};

type NavigatorLike = {
  connection?: NetworkInformationLike;
  mozConnection?: NetworkInformationLike;
  webkitConnection?: NetworkInformationLike;
};

/** localStorage key for the persisted data-saver preference. */
export const DATA_SAVER_KEY = "vergeo:clips-data-saver";

/** Saver is ON until the visitor says otherwise. */
export const DATA_SAVER_DEFAULT = true;

/** The rendition served when saver is on, or when we are unsure. */
export const SAVER_RENDITION = "480p";
export const FULL_RENDITION = "720p";

const WIFI_TYPES = new Set(["wifi", "ethernet"]);
const CELLULAR_TYPES = new Set(["cellular", "wimax"]);

export function readConnection(
  navigatorLike: NavigatorLike | undefined,
): NetworkInformationLike | undefined {
  if (!navigatorLike) {
    return undefined;
  }
  return navigatorLike.connection ?? navigatorLike.mozConnection ?? navigatorLike.webkitConnection;
}

/**
 * Classify the connection. Anything we cannot positively identify as Wi-Fi is
 * "unknown", and `mayAutoplay` treats unknown exactly like cellular.
 */
export function connectionKind(navigatorLike: NavigatorLike | undefined): ConnectionKind {
  const info = readConnection(navigatorLike);
  if (!info) {
    return "unknown";
  }
  if (typeof info.type === "string") {
    const type = info.type.toLowerCase();
    if (WIFI_TYPES.has(type)) {
      return "wifi";
    }
    if (CELLULAR_TYPES.has(type)) {
      return "cellular";
    }
  }
  // `effectiveType` describes speed, not medium: a fast connection may still be
  // metered, so it can identify cellular but must never be read as Wi-Fi.
  if (typeof info.effectiveType === "string") {
    if (["slow-2g", "2g", "3g"].includes(info.effectiveType)) {
      return "cellular";
    }
  }
  return "unknown";
}

/** The browser's own "reduce my data" signal, which we always honour. */
export function browserRequestsSaveData(navigatorLike: NavigatorLike | undefined): boolean {
  return readConnection(navigatorLike)?.saveData === true;
}

export type AutoplayInputs = {
  connection: ConnectionKind;
  dataSaverOn: boolean;
  prefersReducedMotion: boolean;
  inView: boolean;
};

/**
 * Whether *this* clip may start on its own. Every condition must hold; there is
 * no "mostly Wi-Fi" case, and the caller is expected to pass `inView` for at
 * most one clip at a time.
 */
export function mayAutoplay(inputs: AutoplayInputs): boolean {
  if (!inputs.inView) {
    return false;
  }
  if (inputs.dataSaverOn) {
    return false;
  }
  if (inputs.prefersReducedMotion) {
    return false;
  }
  // The whole rule in one line: only a *positively identified* Wi-Fi connection
  // ever autoplays. "unknown" falls through to false with cellular.
  return inputs.connection === "wifi";
}

/** Which rendition to request. Saver — or any doubt — means the smaller file. */
export function preferredRendition(dataSaverOn: boolean, connection: ConnectionKind): string {
  if (dataSaverOn || connection !== "wifi") {
    return SAVER_RENDITION;
  }
  return FULL_RENDITION;
}

/**
 * `preload` for the single `<video>`. Never "auto": preloading a video the
 * visitor has not asked for is the exact cost this feed exists to avoid.
 */
export function preloadMode(dataSaverOn: boolean, connection: ConnectionKind): "none" | "metadata" {
  return dataSaverOn || connection !== "wifi" ? "none" : "metadata";
}

/** Whether the size chip must be shown before play. On anything but Wi-Fi, yes. */
export function requiresSizeChipBeforePlay(connection: ConnectionKind): boolean {
  return connection !== "wifi";
}

export function readStoredDataSaver(storage: Pick<Storage, "getItem"> | undefined): boolean {
  if (!storage) {
    return DATA_SAVER_DEFAULT;
  }
  try {
    const raw = storage.getItem(DATA_SAVER_KEY);
    if (raw === "off") {
      return false;
    }
    if (raw === "on") {
      return true;
    }
  } catch {
    // A blocked storage API must not turn saver off.
  }
  return DATA_SAVER_DEFAULT;
}

export function writeStoredDataSaver(
  storage: Pick<Storage, "setItem"> | undefined,
  on: boolean,
): void {
  try {
    storage?.setItem(DATA_SAVER_KEY, on ? "on" : "off");
  } catch {
    // Preference is a nicety; failing to persist must never break the feed.
  }
}
