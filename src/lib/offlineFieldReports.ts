export interface QueuedFieldReport {
  id: string;
  clientReportId: string;
  lat: number;
  lng: number;
  description: string;
  userId?: string | null;
  createdAt: string;
}

const DB_NAME = 'avalanche-insight-hub-offline';
const DB_VERSION = 1;
const STORE_NAME = 'field_report_queue';
let activeFlushPromise: Promise<number> | null = null;

function ensureIndexedDb(): IDBFactory {
  if (typeof indexedDB === 'undefined') {
    throw new Error('IndexedDB is unavailable in this environment');
  }
  return indexedDB;
}

function openQueueDb(): Promise<IDBDatabase> {
  return new Promise((resolve, reject) => {
    const request = ensureIndexedDb().open(DB_NAME, DB_VERSION);

    request.onupgradeneeded = () => {
      const db = request.result;
      if (!db.objectStoreNames.contains(STORE_NAME)) {
        db.createObjectStore(STORE_NAME, { keyPath: 'id' });
      }
    };

    request.onsuccess = () => resolve(request.result);
    request.onerror = () => reject(request.error ?? new Error('Failed to open offline queue database'));
  });
}

async function withStore<T>(
  mode: IDBTransactionMode,
  handler: (store: IDBObjectStore) => Promise<T> | T,
): Promise<T> {
  const db = await openQueueDb();
  try {
    const tx = db.transaction(STORE_NAME, mode);
    const store = tx.objectStore(STORE_NAME);
    const result = await handler(store);
    await new Promise<void>((resolve, reject) => {
      tx.oncomplete = () => resolve();
      tx.onerror = () => reject(tx.error ?? new Error('Offline queue transaction failed'));
      tx.onabort = () => reject(tx.error ?? new Error('Offline queue transaction aborted'));
    });
    return result;
  } finally {
    db.close();
  }
}

export async function enqueueFieldReport(report: QueuedFieldReport): Promise<void> {
  await withStore('readwrite', (store) => {
    store.put(report);
  });
}

export async function listQueuedFieldReports(): Promise<QueuedFieldReport[]> {
  const db = await openQueueDb();
  try {
    return await new Promise<QueuedFieldReport[]>((resolve, reject) => {
      const tx = db.transaction(STORE_NAME, 'readonly');
      const store = tx.objectStore(STORE_NAME);
      const request = store.getAll();
      request.onsuccess = () => resolve((request.result as QueuedFieldReport[]) || []);
      request.onerror = () => reject(request.error ?? new Error('Failed to read offline queue'));
    });
  } finally {
    db.close();
  }
}

export async function removeQueuedFieldReport(id: string): Promise<void> {
  await withStore('readwrite', (store) => {
    store.delete(id);
  });
}

export async function flushQueuedFieldReports(
  submit: (report: QueuedFieldReport) => Promise<void>,
): Promise<number> {
  if (activeFlushPromise) {
    return activeFlushPromise;
  }

  const flushPromise = (async () => {
    const queued = await listQueuedFieldReports();
    let processed = 0;

    for (const report of queued) {
      await submit(report);
      await removeQueuedFieldReport(report.id);
      processed += 1;
    }

    return processed;
  })();

  activeFlushPromise = flushPromise;
  try {
    return await flushPromise;
  } finally {
    activeFlushPromise = null;
  }
}
