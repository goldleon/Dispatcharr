import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { isChunkLoadError, handleChunkLoadError, CHUNK_RELOAD_KEY } from '../chunkLoad';

describe('chunkLoad utils', () => {
  beforeEach(() => {
    sessionStorage.clear();
    vi.restoreAllMocks();
  });

  afterEach(() => {
    sessionStorage.clear();
    vi.restoreAllMocks();
  });

  it('detects chunk load errors across browser error variations', () => {
    expect(isChunkLoadError(new Error('error loading dynamically imported module: /assets/StreamSettingsForm-BlKc4rkr.js'))).toBe(true);
    expect(isChunkLoadError(new Error('Failed to fetch dynamically imported module: https://example.com/assets/foo.js'))).toBe(true);
    expect(isChunkLoadError(new Error('Importing a module script failed.'))).toBe(true);
    expect(isChunkLoadError(new Error('Failed to load module script'))).toBe(true);
    expect(isChunkLoadError(new Error('Loading chunk 4 failed'))).toBe(true);
    expect(isChunkLoadError(new Error('Normal application error'))).toBe(false);
    expect(isChunkLoadError(null)).toBe(false);
  });

  it('triggers window.location.reload on first chunk error', () => {
    const reloadMock = vi.fn();
    Object.defineProperty(window, 'location', {
      value: { reload: reloadMock },
      writable: true,
    });

    const error = new Error('error loading dynamically imported module: /assets/StreamSettingsForm-BlKc4rkr.js');
    const handled = handleChunkLoadError(error);

    expect(handled).toBe(true);
    expect(reloadMock).toHaveBeenCalledTimes(1);
    expect(sessionStorage.getItem(CHUNK_RELOAD_KEY)).toBeTruthy();
  });

  it('prevents reload loops if reloaded within 15 seconds', () => {
    const reloadMock = vi.fn();
    Object.defineProperty(window, 'location', {
      value: { reload: reloadMock },
      writable: true,
    });

    sessionStorage.setItem(CHUNK_RELOAD_KEY, String(Date.now()));

    const error = new Error('error loading dynamically imported module: /assets/StreamSettingsForm-BlKc4rkr.js');
    const handled = handleChunkLoadError(error);

    expect(handled).toBe(false);
    expect(reloadMock).not.toHaveBeenCalled();
  });
});
