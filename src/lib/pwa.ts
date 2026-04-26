// Story 17: Service-worker registration + offline status tracking.
// The Workbox BackgroundSync queue ("field-report-queue") is configured in
// vite.config.ts — POSTs to /functions/v1/field-report-enrichment and
// /functions/v1/ingest-event are automatically retained while offline and
// replayed on reconnect.

import { flushQueuedFieldReports } from '@/lib/offlineFieldReports';
import { submitQueuedFieldReport } from '@/lib/fieldReportSync';

let queuedFieldReportSyncRegistered = false;

async function flushQueuedFieldReportsOnReconnect(reason: 'startup' | 'online') {
  try {
    const queued = await flushQueuedFieldReports(submitQueuedFieldReport);
    if (queued > 0) {
      console.info(`[pwa] Flushed ${queued} queued field report${queued === 1 ? '' : 's'} on ${reason}.`);
    }
  } catch (error) {
    console.warn('[pwa] queued field report sync failed:', error);
  }
}

export async function initPwa() {
  if (typeof window === 'undefined') return;
  if (!('serviceWorker' in navigator)) return;

  if (!queuedFieldReportSyncRegistered) {
    queuedFieldReportSyncRegistered = true;
    window.addEventListener('online', () => {
      void flushQueuedFieldReportsOnReconnect('online');
    });
    if (navigator.onLine) {
      void flushQueuedFieldReportsOnReconnect('startup');
    }
  }

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
