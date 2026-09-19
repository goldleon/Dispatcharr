import { lazy } from 'react';
import { handleChunkLoadError } from './chunkLoad';

/**
 * Wrapper around React.lazy that detects chunk loading errors from new
 * deployments and auto-reloads the page to fetch the fresh bundle.
 */
export const lazyWithRetry = (componentImport) => {
  return lazy(async () => {
    try {
      return await componentImport();
    } catch (error) {
      if (handleChunkLoadError(error)) {
        // Return a promise that never resolves while the page is reloading
        return new Promise(() => {});
      }
      throw error;
    }
  });
};
