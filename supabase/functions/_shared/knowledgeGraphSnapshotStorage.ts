import {
  buildApprovedGraphContext,
  type ServerOwnedGraphSnapshotEnvelope,
} from './knowledgeGraphSnapshot.ts';

export const KNOWLEDGE_GRAPH_SNAPSHOT_BUCKET = 'knowledge-graph-snapshots';
export const MAX_GRAPH_SNAPSHOT_BYTES = 50 * 1024 * 1024;
export const MAX_GRAPH_SNAPSHOT_MANIFEST_BYTES = 1024 * 1024;

const SNAPSHOT_ID_PATTERN = /^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$/;

export interface StorageDownloadResult {
  data: Blob | null;
  error: { message?: string } | null;
}

export interface SnapshotStorageClient {
  storage: {
    from(bucket: string): {
      download(path: string): Promise<StorageDownloadResult>;
    };
  };
}

export interface KnowledgeGraphSnapshotStoragePaths {
  manifestPath: string;
  graphPath: string;
}

export function isSafeKnowledgeGraphSnapshotId(snapshotId: string): boolean {
  return SNAPSHOT_ID_PATTERN.test(snapshotId);
}

export function getKnowledgeGraphSnapshotStoragePaths(
  snapshotId: string,
): KnowledgeGraphSnapshotStoragePaths {
  if (!isSafeKnowledgeGraphSnapshotId(snapshotId)) {
    throw new Error('Invalid knowledge-graph snapshot identifier');
  }
  return {
    manifestPath: `${snapshotId}/manifest.json`,
    graphPath: `${snapshotId}/graph.json`,
  };
}

export async function sha256Hex(bytes: Uint8Array): Promise<string> {
  const input = new Uint8Array(bytes.byteLength);
  input.set(bytes);
  const digest = await crypto.subtle.digest('SHA-256', input.buffer as ArrayBuffer);
  return Array.from(new Uint8Array(digest))
    .map((byte) => byte.toString(16).padStart(2, '0'))
    .join('');
}

async function downloadBytes(
  supabase: SnapshotStorageClient,
  path: string,
  maxBytes: number,
): Promise<Uint8Array> {
  const { data, error } = await supabase.storage
    .from(KNOWLEDGE_GRAPH_SNAPSHOT_BUCKET)
    .download(path);

  if (error || !data) {
    throw new Error(error?.message || `Missing knowledge-graph snapshot object: ${path}`);
  }
  if (data.size > maxBytes) {
    throw new Error(`Knowledge-graph snapshot object exceeds the ${maxBytes}-byte limit`);
  }

  const bytes = new Uint8Array(await data.arrayBuffer());
  if (bytes.byteLength > maxBytes) {
    throw new Error(`Knowledge-graph snapshot object exceeds the ${maxBytes}-byte limit`);
  }
  return bytes;
}

function parseJson(bytes: Uint8Array, path: string): unknown {
  try {
    return JSON.parse(new TextDecoder().decode(bytes));
  } catch {
    throw new Error(`Invalid JSON in knowledge-graph snapshot object: ${path}`);
  }
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return Boolean(value) && typeof value === 'object' && !Array.isArray(value);
}

/**
 * Load a server-owned graph snapshot from the private storage bucket.
 *
 * The caller supplies a trusted, operator-configured snapshot id; it is never
 * taken from the request body. The raw graph bytes are hashed before parsing
 * and must match the manifest. The existing snapshot adapter then performs the
 * structural, count, denylist, and worktree-dirty checks before this function
 * returns an envelope marked hashVerified=true.
 */
export async function loadServerOwnedGraphSnapshot(
  supabase: SnapshotStorageClient,
  snapshotId: string,
): Promise<ServerOwnedGraphSnapshotEnvelope> {
  const paths = getKnowledgeGraphSnapshotStoragePaths(snapshotId);
  const manifestBytes = await downloadBytes(
    supabase,
    paths.manifestPath,
    MAX_GRAPH_SNAPSHOT_MANIFEST_BYTES,
  );
  const graphBytes = await downloadBytes(
    supabase,
    paths.graphPath,
    MAX_GRAPH_SNAPSHOT_BYTES,
  );
  const manifest = parseJson(manifestBytes, paths.manifestPath);
  const graph = parseJson(graphBytes, paths.graphPath);

  if (!isRecord(manifest) || manifest.snapshotId !== snapshotId) {
    throw new Error('Knowledge-graph snapshot manifest identifier mismatch');
  }

  const graphHash = await sha256Hex(graphBytes);
  if (manifest.graphSha256 !== graphHash) {
    throw new Error('Knowledge-graph snapshot hash mismatch');
  }

  const envelope = {
    graph,
    manifest,
    hashVerified: true,
  };
  if (!buildApprovedGraphContext(envelope)) {
    throw new Error('Knowledge-graph snapshot failed structural approval checks');
  }

  return envelope as ServerOwnedGraphSnapshotEnvelope;
}
