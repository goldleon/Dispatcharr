import React from 'react';
import ReactDOM from 'react-dom/client';
import App from './App';
import { handleChunkLoadError } from './utils/chunkLoad';

// Auto-reload when a deployment replaces hashed chunks
window.addEventListener('vite:preloadError', (event) => {
  if (handleChunkLoadError(event?.payload || event)) {
    event.preventDefault();
  }
});

ReactDOM.createRoot(document.getElementById('root')).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>
);
