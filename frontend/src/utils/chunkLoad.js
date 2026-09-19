/**
 * Utilities for detecting and recovering from stale dynamic import/chunk errors
 * caused by application deployments replacing hashed asset bundles.
 */

export const isChunkLoadError = (error) => {
  if (!error) return false;
  const message = error?.message || String(error);
  return (
    /loading dynamically imported module/i.test(message) ||
    /failed to fetch dynamically imported module/i.test(message) ||
    /failed to load module script/i.test(message) ||
    /importing a module script failed/i.test(message) ||
    /unable to preload/i.test(message) ||
    /chunk.*failed/i.test(message) ||
    /dynamically imported module/i.test(message)
  );
};

export const CHUNK_RELOAD_KEY = 'dispatcharr_chunk_reload';

export const handleChunkLoadError = (error) => {
  if (!isChunkLoadError(error)) return false;

  try {
    const lastReload = sessionStorage.getItem(CHUNK_RELOAD_KEY);
    const now = Date.now();
    // Prevent reload loops: only auto-reload once within a 15-second window
    if (!lastReload || now - parseInt(lastReload, 10) > 15000) {
      sessionStorage.setItem(CHUNK_RELOAD_KEY, String(now));
      window.location.reload();
      return true;
    }
  } catch {
    // If sessionStorage is unavailable (strict privacy mode), fallback to one reload
    window.location.reload();
    return true;
  }

  return false;
};
