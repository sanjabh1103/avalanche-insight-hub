import { supabase } from '@/integrations/supabase/client';
import type { ForecastBulletin } from '@/lib/forecastBulletins';

function parseStorageRef(ref: string): { bucket: string; objectPath: string } {
  const [bucket, ...rest] = ref.split('/');
  if (!bucket || rest.length === 0) {
    throw new Error(`Invalid storage ref: ${ref}`);
  }
  return { bucket, objectPath: rest.join('/') };
}

async function blobToText(blob: Blob, compressed: boolean): Promise<string> {
  if (!compressed) {
    return await blob.text();
  }
  const decompressor = typeof DecompressionStream !== 'undefined'
    ? new DecompressionStream('gzip')
    : null;
  if (!decompressor) {
    throw new Error('Browser does not support gzip decompression for forecast artifacts');
  }
  const stream = blob.stream().pipeThrough(decompressor);
  return await new Response(stream).text();
}

async function downloadJson<T>(storageRef: string): Promise<T> {
  const { bucket, objectPath } = parseStorageRef(storageRef);
  const { data, error } = await supabase.storage.from(bucket).download(objectPath);
  if (error || !data) {
    throw new Error(error?.message || `Failed to download ${storageRef}`);
  }
  const text = await blobToText(data, storageRef.endsWith('.gz'));
  return JSON.parse(text) as T;
}

export interface ForecastArtifactHour {
  forecastHour: number;
  validTime: string;
  storageRef: string;
  cellCount: number;
  readyCellCount: number;
  staleCellCount: number;
  payloadSha256?: string;
}

export interface ForecastArtifactManifest {
  schemaVersion: string;
  forecastRunId: string;
  hazardType: string;
  regionKey: string;
  regionName: string;
  forecastDate: string;
  issueTime: string;
  horizonHours: number;
  gridSize: number;
  bbox: number[];
  status: string;
  weatherSummary: unknown;
  forecastBulletin?: ForecastBulletin | null;
  modelMetadata: Record<string, unknown>;
  runoutStorageRef?: string | null;
  hours: ForecastArtifactHour[];
}

export interface ForecastArtifactHourPayload {
  schema_version: string;
  forecast_run_id: string;
  region_key: string;
  forecast_date: string;
  forecast_hour: number;
  valid_time: string;
  cells: unknown[];
}

export interface ForecastArtifactRunoutsPayload {
  schema_version: string;
  forecast_run_id: string;
  region_key: string;
  forecast_date: string;
  runout_polygons: Array<Record<string, unknown>>;
}

export async function loadForecastManifest(storageRef: string): Promise<ForecastArtifactManifest> {
  return await downloadJson<ForecastArtifactManifest>(storageRef);
}

export async function loadForecastHourPayload(storageRef: string): Promise<ForecastArtifactHourPayload> {
  return await downloadJson<ForecastArtifactHourPayload>(storageRef);
}

export async function loadForecastRunouts(storageRef: string): Promise<ForecastArtifactRunoutsPayload> {
  return await downloadJson<ForecastArtifactRunoutsPayload>(storageRef);
}
