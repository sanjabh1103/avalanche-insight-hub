type ForecastRunArtifactRow = {
  id: string;
  created_at: string;
  forecast_date: string;
  compatibility_forecast_grid_id: string | null;
  manifest_storage_ref: string | null;
  bbox: number[];
};

type ForecastArtifactManifestHour = {
  forecastHour: number;
  storageRef: string;
};

type ForecastArtifactManifest = {
  issueTime: string;
  bbox: number[];
  hours: ForecastArtifactManifestHour[];
};

type ForecastArtifactHourPayload = {
  cells: unknown[];
};

function parseStorageRef(ref: string): { bucket: string; objectPath: string } {
  const [bucket, ...rest] = ref.split('/');
  if (!bucket || rest.length === 0) {
    throw new Error(`Invalid storage ref: ${ref}`);
  }
  return { bucket, objectPath: rest.join('/') };
}

async function blobToText(blob: Blob, compressed: boolean): Promise<string> {
  if (!compressed) return await blob.text();
  const decompressor = typeof DecompressionStream !== 'undefined'
    ? new DecompressionStream('gzip')
    : null;
  if (!decompressor) {
    throw new Error('Runtime does not support gzip decompression for forecast artifacts');
  }
  const stream = blob.stream().pipeThrough(decompressor);
  return await new Response(stream).text();
}

export async function downloadStorageJson<T>(supabase: any, storageRef: string): Promise<T> {
  const { bucket, objectPath } = parseStorageRef(storageRef);
  const { data, error } = await supabase.storage.from(bucket).download(objectPath);
  if (error || !data) {
    throw new Error(error?.message || `Failed to download ${storageRef}`);
  }
  const text = await blobToText(data as Blob, storageRef.endsWith('.gz'));
  return JSON.parse(text) as T;
}

export async function fetchPublishedRunByCompatibilityForecastGridId(
  supabase: any,
  forecastGridId: string,
): Promise<ForecastRunArtifactRow | null> {
  const { data, error } = await supabase
    .from('forecast_runs')
    .select('id, created_at, forecast_date, compatibility_forecast_grid_id, manifest_storage_ref, bbox')
    .eq('compatibility_forecast_grid_id', forecastGridId)
    .order('created_at', { ascending: false })
    .limit(1)
    .maybeSingle();
  if (error) throw error;
  return (data as ForecastRunArtifactRow | null) ?? null;
}

export async function loadHourlyGridsFromForecastRun(
  supabase: any,
  manifestStorageRef: string,
): Promise<{ bbox: number[]; created_at: string; hourly_grids: any[][] }> {
  const manifest = await downloadStorageJson<ForecastArtifactManifest>(supabase, manifestStorageRef);
  const hours = await Promise.all(
    (manifest.hours || []).map(async (hour) => {
      const payload = await downloadStorageJson<ForecastArtifactHourPayload>(supabase, hour.storageRef);
      return Array.isArray(payload.cells) ? payload.cells : [];
    }),
  );
  return {
    bbox: Array.isArray(manifest.bbox) ? manifest.bbox : [0, 0, 0, 0],
    created_at: manifest.issueTime,
    hourly_grids: hours,
  };
}
