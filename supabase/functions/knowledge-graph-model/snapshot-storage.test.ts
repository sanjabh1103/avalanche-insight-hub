import { assert, assertEquals, assertRejects } from 'https://deno.land/std@0.224.0/assert/mod.ts';

import type {
  SnapshotStorageClient,
  StorageDownloadResult,
} from '../_shared/knowledgeGraphSnapshotStorage.ts';
import {
  getKnowledgeGraphSnapshotStoragePaths,
  KNOWLEDGE_GRAPH_SNAPSHOT_BUCKET,
  loadServerOwnedGraphSnapshot,
  MAX_GRAPH_SNAPSHOT_BYTES,
  sha256Hex,
} from '../_shared/knowledgeGraphSnapshotStorage.ts';

const SNAPSHOT_ID = 'snapshot-1';

function makeClient(files: Record<string, string>): SnapshotStorageClient {
  return {
    storage: {
      from(bucket: string) {
        assertEquals(bucket, KNOWLEDGE_GRAPH_SNAPSHOT_BUCKET);
        return {
          async download(path: string): Promise<StorageDownloadResult> {
            const contents = files[path];
            if (contents === undefined) {
              return { data: null, error: { message: `missing:${path}` } };
            }
            return {
              data: new Blob([contents], { type: 'application/json' }),
              error: null,
            };
          },
        };
      },
    },
  };
}

async function makeSnapshot() {
  const graphText = JSON.stringify({
    nodes: [
      { id: 'file:src/App.tsx', filePath: 'src/App.tsx', sourceSha256: 'b'.repeat(64) },
      { id: 'file:src/main.tsx', filePath: 'src/main.tsx', sourceSha256: 'c'.repeat(64) },
    ],
    edges: [{ source: 'file:src/App.tsx', target: 'file:src/main.tsx', type: 'imports' }],
  });
  const graphSha256 = await sha256Hex(new TextEncoder().encode(graphText));
  const paths = getKnowledgeGraphSnapshotStoragePaths(SNAPSHOT_ID);
  return {
    graphText,
    files: {
      [paths.manifestPath]: JSON.stringify({
        snapshotId: SNAPSHOT_ID,
        graphSha256,
        nodeCount: 2,
        edgeCount: 1,
        worktreeDirty: false,
      }),
      [paths.graphPath]: graphText,
    },
  };
}

Deno.test('server-owned loader verifies raw graph bytes and returns approved envelope', async () => {
  const snapshot = await makeSnapshot();
  const loaded = await loadServerOwnedGraphSnapshot(makeClient(snapshot.files), SNAPSHOT_ID);

  assert(loaded.hashVerified);
  assertEquals(loaded.manifest.snapshotId, SNAPSHOT_ID);
  assertEquals(loaded.manifest.nodeCount, 2);
  assertEquals(loaded.graph.nodes.length, 2);
  assertEquals(loaded.graph.edges.length, 1);
});

Deno.test('server-owned loader rejects a manifest hash mismatch', async () => {
  const snapshot = await makeSnapshot();
  const paths = getKnowledgeGraphSnapshotStoragePaths(SNAPSHOT_ID);
  const files = {
    ...snapshot.files,
    [paths.manifestPath]: JSON.stringify({
      snapshotId: SNAPSHOT_ID,
      graphSha256: '0'.repeat(64),
      nodeCount: 2,
      edgeCount: 1,
      worktreeDirty: false,
    }),
  };

  await assertRejects(
    () => loadServerOwnedGraphSnapshot(makeClient(files), SNAPSHOT_ID),
    Error,
    'hash mismatch',
  );
});

Deno.test('server-owned loader rejects unsafe snapshot identifiers before storage access', async () => {
  await assertRejects(
    () => loadServerOwnedGraphSnapshot(makeClient({}), '../snapshot-1'),
    Error,
    'identifier',
  );
});

Deno.test('server-owned loader rejects missing snapshot objects', async () => {
  const snapshot = await makeSnapshot();
  const paths = getKnowledgeGraphSnapshotStoragePaths(SNAPSHOT_ID);
  await assertRejects(
    () =>
      loadServerOwnedGraphSnapshot(
        makeClient({ [paths.manifestPath]: snapshot.files[paths.manifestPath] }),
        SNAPSHOT_ID,
      ),
    Error,
    'missing',
  );
});

Deno.test('server-owned loader rejects oversized graph objects before parsing', async () => {
  const snapshot = await makeSnapshot();
  const paths = getKnowledgeGraphSnapshotStoragePaths(SNAPSHOT_ID);
  const oversizedBlob = {
    size: MAX_GRAPH_SNAPSHOT_BYTES + 1,
    arrayBuffer: async () => new ArrayBuffer(0),
  } as unknown as Blob;
  const client: SnapshotStorageClient = {
    storage: {
      from() {
        return {
          async download(path: string): Promise<StorageDownloadResult> {
            if (path === paths.manifestPath) {
              return {
                data: new Blob([snapshot.files[paths.manifestPath]], {
                  type: 'application/json',
                }),
                error: null,
              };
            }
            return { data: oversizedBlob, error: null };
          },
        };
      },
    },
  };

  await assertRejects(
    () => loadServerOwnedGraphSnapshot(client, SNAPSHOT_ID),
    Error,
    'limit',
  );
});

Deno.test('server-owned loader rejects dirty snapshots through the production adapter', async () => {
  const snapshot = await makeSnapshot();
  const paths = getKnowledgeGraphSnapshotStoragePaths(SNAPSHOT_ID);
  const dirtyManifest = JSON.stringify({
    snapshotId: SNAPSHOT_ID,
    graphSha256: await sha256Hex(new TextEncoder().encode(snapshot.graphText)),
    nodeCount: 2,
    edgeCount: 1,
    worktreeDirty: true,
  });

  await assertRejects(
    () =>
      loadServerOwnedGraphSnapshot(
        makeClient({ ...snapshot.files, [paths.manifestPath]: dirtyManifest }),
        SNAPSHOT_ID,
      ),
    Error,
    'approval',
  );
});
