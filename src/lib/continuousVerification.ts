import { supabase } from '@/integrations/supabase/client';

export interface ContinuousVerificationDashboardData {
  coverage?: {
    total_cells?: number;
    cells_with_3plus_sources?: number;
    cells_with_baselines?: number;
    cells_with_anomaly_state?: number;
  };
  stale_cells?: {
    count?: number;
    top_stale?: Array<{ cell_id: string; max_freshness_hours: number }>;
  };
  disagreement?: {
    anomaly_count?: number;
    attribution_breakdown?: Record<string, number>;
  };
  source_health?: Array<{
    sensor: string;
    last_acquisition?: string;
    avg_latency_hours?: number;
    gap_count?: number;
  }>;
  model_drift?: {
    calibration_drift?: number;
    brier_trend?: number[];
  };
  review_backlog?: {
    pending_count?: number;
    oldest_pending_hours?: number;
    scientist_throughput?: number;
  };
}

export type ContinuousVerificationLoadResult = {
  status: 'available' | 'unavailable';
  data?: ContinuousVerificationDashboardData;
  unavailable_reason?: string;
  truncated_tables?: string[];
};

type QueryError = { code?: string; message?: string; status?: number } | null;
type QueryResult = { data: unknown; error: QueryError };
type Query = PromiseLike<QueryResult> & {
  select: (columns?: string) => Query;
  limit: (count: number) => Query;
};

const db = supabase as unknown as { from: (table: string) => Query };
const STALE_THRESHOLD_HOURS = 72;
const MAX_ROWS = 1000;
const FETCH_TIMEOUT_MS = 8000;

function records(value: unknown): Array<Record<string, unknown>> {
  return Array.isArray(value)
    ? value.filter((row): row is Record<string, unknown> => Boolean(row) && typeof row === 'object' && !Array.isArray(row))
    : [];
}

function finiteNumber(value: unknown): number | null {
  if (typeof value === 'boolean' || value == null || value === '') return null;
  const numeric = Number(value);
  return Number.isFinite(numeric) ? numeric : null;
}

function isMissingTable(error: QueryError): boolean {
  const message = String(error?.message ?? '').toLowerCase();
  return error?.code === '42P01' || error?.status === 404 || message.includes('does not exist');
}

async function fetchRows(table: string): Promise<Array<Record<string, unknown>>> {
  const controller = new AbortController();
  const timeoutId = window.setTimeout(() => controller.abort(), FETCH_TIMEOUT_MS);
  try {
    const query = db.from(table).select('*').limit(MAX_ROWS);
    const racePromise = Promise.race([
      query,
      new Promise<never>((_, reject) => {
        controller.signal.addEventListener('abort', () =>
          reject(new Error(`${table} request timed out after ${FETCH_TIMEOUT_MS}ms`)),
        );
      }),
    ]);
    const { data, error } = await racePromise;
    if (error) {
      throw new Error(isMissingTable(error) ? `${table} is unavailable until its migration is applied` : error.message ?? `Unable to read ${table}`);
    }
    return records(data);
  } finally {
    window.clearTimeout(timeoutId);
  }
}

function isTruncated(rows: Array<Record<string, unknown>>): boolean {
  return rows.length >= MAX_ROWS;
}

function ageHours(timestamp: unknown, now: number): number | null {
  if (typeof timestamp !== 'string') return null;
  const parsed = Date.parse(timestamp);
  if (!Number.isFinite(parsed)) return null;
  return Math.max(0, (now - parsed) / 3_600_000);
}

export function buildContinuousVerificationDashboardData(
  observations: Array<Record<string, unknown>>,
  baselines: Array<Record<string, unknown>>,
  anomalies: Array<Record<string, unknown>>,
  reviewQueue: Array<Record<string, unknown>>,
  validationCases: Array<Record<string, unknown>>,
  now = Date.now(),
): ContinuousVerificationDashboardData {
  const allCells = new Set<string>();
  const independentSensors = new Map<string, Set<string>>();
  const staleByCell = new Map<string, number>();
  const sourceStats = new Map<string, { latest: string | undefined; latency: number[]; gaps: number }>();

  observations.forEach((observation) => {
    const cellId = String(observation.cell_id ?? '').trim();
    const sensor = String(observation.sensor ?? '').trim();
    if (!cellId) return;
    allCells.add(cellId);
    const freshness = finiteNumber(observation.freshness_hours);
    const stale = freshness == null || freshness > STALE_THRESHOLD_HOURS;
    const synthetic = observation.synthetic === true;
    const quality = String(observation.quality_state ?? '').toLowerCase();
    const independent = !synthetic && quality !== 'rejected' && quality !== 'missing';
    if (independent && sensor) {
      const sensors = independentSensors.get(cellId) ?? new Set<string>();
      sensors.add(sensor);
      independentSensors.set(cellId, sensors);
    }
    if (stale) staleByCell.set(cellId, Math.max(staleByCell.get(cellId) ?? 0, freshness ?? STALE_THRESHOLD_HOURS + 1));

    if (sensor) {
      const stats = sourceStats.get(sensor) ?? { latest: undefined, latency: [], gaps: 0 };
      const acquisition = typeof observation.acquisition_time === 'string' ? observation.acquisition_time : undefined;
      if (acquisition && (!stats.latest || acquisition > stats.latest)) stats.latest = acquisition;
      if (freshness != null) stats.latency.push(freshness);
      if (stale || synthetic || quality !== 'verified') stats.gaps += 1;
      sourceStats.set(sensor, stats);
    }
  });

  const topStale = [...staleByCell.entries()]
    .sort(([, a], [, b]) => b - a)
    .slice(0, 10)
    .map(([cell_id, max_freshness_hours]) => ({ cell_id, max_freshness_hours }));

  const baselineCells = new Set(
    baselines.map((row) => String(row.cell_id ?? '').trim()).filter(Boolean),
  );
  const anomalyCells = new Set(
    anomalies.map((row) => String(row.cell_id ?? '').trim()).filter(Boolean),
  );
  const attributionBreakdown: Record<string, number> = {};
  anomalies.forEach((row) => {
    const bucket = String(row.attribution_bucket ?? 'unattributed').trim() || 'unattributed';
    attributionBreakdown[bucket] = (attributionBreakdown[bucket] ?? 0) + 1;
  });

  const pendingCases = validationCases.filter((row) => ['pending', 'in_review'].includes(String(row.status ?? '')));
  const pendingQueue = reviewQueue.filter((row) => ['pending', 'assigned'].includes(String(row.review_state ?? '')));
  const pendingRows = pendingCases.length > 0 ? pendingCases : pendingQueue;
  const pendingAges = pendingRows
    .map((row) => ageHours(row.created_at, now))
    .filter((value): value is number => value != null);
  const weekStart = now - 7 * 24 * 3_600_000;
  const scientistThroughput = validationCases.filter((row) => {
    const reviewedAt = Date.parse(String(row.reviewed_at ?? ''));
    return Number.isFinite(reviewedAt) && reviewedAt >= weekStart;
  }).length;

  return {
    coverage: {
      total_cells: allCells.size,
      cells_with_3plus_sources: [...independentSensors.values()].filter((sensors) => sensors.size >= 3).length,
      cells_with_baselines: [...baselineCells].filter((cell) => allCells.has(cell)).length,
      cells_with_anomaly_state: anomalyCells.size,
    },
    stale_cells: { count: staleByCell.size, top_stale: topStale },
    disagreement: { anomaly_count: anomalies.length, attribution_breakdown: attributionBreakdown },
    source_health: [...sourceStats.entries()].sort(([a], [b]) => a.localeCompare(b)).map(([sensor, stats]) => ({
      sensor,
      last_acquisition: stats.latest,
      avg_latency_hours: stats.latency.length
        ? stats.latency.reduce((sum, value) => sum + value, 0) / stats.latency.length
        : undefined,
      gap_count: stats.gaps,
    })),
    // Calibration drift is intentionally unavailable here: it must come from
    // a held-out evaluation artifact, never from dashboard display data.
    model_drift: {},
    review_backlog: {
      pending_count: pendingRows.length,
      oldest_pending_hours: pendingAges.length ? Math.max(...pendingAges) : undefined,
      scientist_throughput: scientistThroughput,
    },
  };
}

export async function loadContinuousVerificationDashboard(): Promise<ContinuousVerificationLoadResult> {
  try {
    const [observations, baselines, anomalies, reviewQueue, validationCases] = await Promise.all([
      fetchRows('verification_observations'),
      fetchRows('verification_baselines'),
      fetchRows('verification_anomalies'),
      fetchRows('verification_review_queue'),
      fetchRows('scientist_validation_cases'),
    ]);
    const truncated_tables: string[] = [];
    if (isTruncated(observations)) truncated_tables.push('verification_observations');
    if (isTruncated(baselines)) truncated_tables.push('verification_baselines');
    if (isTruncated(anomalies)) truncated_tables.push('verification_anomalies');
    if (isTruncated(reviewQueue)) truncated_tables.push('verification_review_queue');
    if (isTruncated(validationCases)) truncated_tables.push('scientist_validation_cases');
    return {
      status: 'available',
      data: buildContinuousVerificationDashboardData(observations, baselines, anomalies, reviewQueue, validationCases),
      truncated_tables: truncated_tables.length > 0 ? truncated_tables : undefined,
    };
  } catch (error) {
    return {
      status: 'unavailable',
      unavailable_reason: error instanceof Error ? error.message : 'Verification data is unavailable',
    };
  }
}
