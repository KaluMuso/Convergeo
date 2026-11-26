/**
 * Recover from a stale-deploy chunk error with one full reload.
 *
 * After a new deploy, a page that was loaded from the previous build can ask
 * for a JS chunk that no longer exists (404 / wrong MIME type). Next.js then
 * throws `ChunkLoadError` and the route error boundary shows "500 Something
 * went wrong". A single hard reload fetches the new HTML and its chunks.
 *
 * Guarded by sessionStorage so a chunk that is genuinely missing can never
 * cause a reload loop: at most one automatic reload per 60 seconds.
 */
const RELOAD_KEY = "vergeo:chunk-reload-at";
const RELOAD_GUARD_MS = 60_000;

const CHUNK_ERROR_PATTERN =
  /ChunkLoadError|Loading (?:CSS )?chunk [\w-]+ failed|Failed to fetch dynamically imported module|Importing a module script failed/i;

export function isChunkLoadError(error: unknown): boolean {
  if (!error) return false;
  if (typeof error === "string") return CHUNK_ERROR_PATTERN.test(error);
  if (typeof error === "object") {
    const { name, message } = error as { name?: unknown; message?: unknown };
    if (name === "ChunkLoadError") return true;
    if (typeof message === "string" && CHUNK_ERROR_PATTERN.test(message)) return true;
  }
  return false;
}

type ReloadEnv = {
  storage?: Pick<Storage, "getItem" | "setItem"> | null;
  now?: () => number;
  reload?: () => void;
};

/** Returns true when a reload was triggered. */
export function reloadOnceForChunkError(error: unknown, env: ReloadEnv = {}): boolean {
  if (!isChunkLoadError(error)) return false;
  const now = env.now ?? Date.now;
  let storage: ReloadEnv["storage"] = env.storage;
  if (storage === undefined) {
    try {
      storage = typeof window === "undefined" ? null : window.sessionStorage;
    } catch {
      storage = null;
    }
  }
  try {
    const last = Number(storage?.getItem(RELOAD_KEY) ?? 0);
    if (last && now() - last < RELOAD_GUARD_MS) return false;
    storage?.setItem(RELOAD_KEY, String(now()));
  } catch {
    // Storage blocked (private mode): never auto-reload, so a genuinely
    // missing chunk cannot loop. The error page's retry still works.
    return false;
  }
  if (!storage) return false;
  const reload = env.reload ?? (() => window.location.reload());
  reload();
  return true;
}
