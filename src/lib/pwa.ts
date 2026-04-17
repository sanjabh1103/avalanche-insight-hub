// Story 17: Service-worker registration + offline status tracking.
// The Workbox BackgroundSync queue ("ingest-event-queue") is configured in
// vite.config.ts — POSTs to /functions/v1/ingest-event are automatically
// retained while offline and replayed on reconnect.

export async function initPwa() {
  if (typeof window === 'undefined') return;
  if (!('serviceWorker' in navigator)) return;

  try {
    const { registerSW } = await import('virtual:pwa-register');
    registerSW({
      immediate: true,
      onOfflineReady: () => {
        // No toast here; handled by the in-app offline banner.
        console.info('[pwa] Offline-ready: field reports can now be queued while offline.');
      },
      onRegistered: (registration) => {
        if (registration) {
          console.info('[pwa] Service worker registered.');
        }
      },
      onRegisterError: (error) => {
        console.warn('[pwa] Service worker registration error:', error);
      },
    });
  } catch (error) {
    // Vite may not have generated the virtual module in some dev scenarios.
    console.warn('[pwa] PWA registration skipped:', error);
  }
}
