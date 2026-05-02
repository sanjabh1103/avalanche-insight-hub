export interface ForecastBulletinDaypart {
  window: string;
  day_index: number;
  daypart: string;
  danger_level: number;
  danger_label: string;
  primary_problem: string;
  problems: string[];
  forecast_hours: number[];
  local_start?: string;
  local_end?: string;
  selected_forecast_hour?: number;
  selected_hour_local_start?: string;
  selected_hour_local_end?: string;
  daypart_aggregation_mode?: string;
  window_frequency_basis?: string;
}

export interface ForecastBulletin {
  schema_version: string;
  standard: string;
  danger_level: number;
  danger_label: string;
  primary_problem: string;
  problems: string[];
  critical_elevations: {
    min_m: number | null;
    max_m: number | null;
    band_step_m: number;
  };
  critical_aspects: string[];
  coverage: 'ready' | 'partial';
  issue_window_policy?: string;
  primary_window?: string;
  primary_window_policy?: string;
  peak_window?: {
    window: string;
    danger_level: number;
    danger_label: string;
    primary_problem: string;
    forecast_hours: number[];
    local_start: string;
    local_end: string;
    selected_forecast_hour?: number;
    selected_hour_local_start?: string;
    selected_hour_local_end?: string;
  };
  dayparts?: ForecastBulletinDaypart[];
  double_map?: boolean;
  aggregation_notes?: string[];
  public_mask_profile?: Record<string, unknown>;
  frequency_threshold_profile?: string;
  derived_from: {
    aggregation: string;
    source_field: string;
    base_metric?: string;
    terrain_filter_profile?: string;
    frequency_basis?: string;
    frequency_class?: string;
    ready_cell_count: number;
    eligible_cell_count?: number;
    max_danger_cell_count: number;
    selected_level_cell_count?: number;
    selected_level_cell_share?: number;
    problem_counts: Record<string, number>;
  };
}

export const EAWS_DANGER_LABELS: Record<number, string> = {
  1: 'Low',
  2: 'Moderate',
  3: 'Considerable',
  4: 'High',
  5: 'Very High',
};

export const BULLETIN_DAYPART_ORDER = ['night', 'morning', 'afternoon', 'evening'] as const;

export function normalizeForecastBulletin(value: unknown): ForecastBulletin | null {
  if (!value || typeof value !== 'object' || Array.isArray(value)) return null;
  const row = value as Record<string, unknown>;
  if (typeof row.danger_level !== 'number' || !Number.isFinite(row.danger_level)) return null;
  if (typeof row.primary_problem !== 'string') return null;
  if (!row.critical_elevations || typeof row.critical_elevations !== 'object') return null;
  if (!Array.isArray(row.critical_aspects)) return null;
  const elevations = row.critical_elevations as Record<string, unknown>;
  const derived = row.derived_from && typeof row.derived_from === 'object'
    ? row.derived_from as Record<string, unknown>
    : {};
  return {
    schema_version: typeof row.schema_version === 'string' ? row.schema_version : 'forecast-bulletin/v1',
    standard: typeof row.standard === 'string' ? row.standard : 'EAWS-style experimental',
    danger_level: Number(row.danger_level),
    danger_label: typeof row.danger_label === 'string'
      ? row.danger_label
      : (EAWS_DANGER_LABELS[Number(row.danger_level)] ?? 'Unknown'),
    primary_problem: String(row.primary_problem),
    problems: Array.isArray(row.problems) ? row.problems.map(String) : [],
    critical_elevations: {
      min_m: typeof elevations.min_m === 'number'
        ? Number(elevations.min_m)
        : null,
      max_m: typeof elevations.max_m === 'number'
        ? Number(elevations.max_m)
        : null,
      band_step_m: typeof elevations.band_step_m === 'number'
        ? Number(elevations.band_step_m)
        : 200,
    },
    critical_aspects: row.critical_aspects.map(String),
    coverage: row.coverage === 'partial' ? 'partial' : 'ready',
    issue_window_policy: typeof row.issue_window_policy === 'string' ? row.issue_window_policy : undefined,
    primary_window: typeof row.primary_window === 'string' ? row.primary_window : undefined,
    primary_window_policy: typeof row.primary_window_policy === 'string' ? row.primary_window_policy : undefined,
    peak_window: normalizePeakWindow(row.peak_window),
    dayparts: Array.isArray(row.dayparts)
      ? row.dayparts
        .map((item) => normalizeDaypart(item))
        .filter((item): item is ForecastBulletinDaypart => item !== undefined)
      : undefined,
    double_map: typeof row.double_map === 'boolean' ? row.double_map : undefined,
    aggregation_notes: Array.isArray(row.aggregation_notes) ? row.aggregation_notes.map(String) : undefined,
    public_mask_profile: row.public_mask_profile && typeof row.public_mask_profile === 'object' && !Array.isArray(row.public_mask_profile)
      ? row.public_mask_profile as Record<string, unknown>
      : undefined,
    frequency_threshold_profile: typeof row.frequency_threshold_profile === 'string' ? row.frequency_threshold_profile : undefined,
    derived_from: {
      aggregation: typeof derived.aggregation === 'string'
        ? String(derived.aggregation)
        : 'highest_regional_level_by_cumulative_frequency',
      source_field: typeof derived.source_field === 'string'
        ? String(derived.source_field)
        : 'risk_score',
      base_metric: typeof derived.base_metric === 'string'
        ? String(derived.base_metric)
        : 'probability_risk_score',
      terrain_filter_profile: typeof derived.terrain_filter_profile === 'string'
        ? String(derived.terrain_filter_profile)
        : 'apt_30_50_v1',
      frequency_basis: typeof derived.frequency_basis === 'string'
        ? String(derived.frequency_basis)
        : 'cumulative_ge_threshold',
      frequency_class: typeof derived.frequency_class === 'string'
        ? String(derived.frequency_class)
        : undefined,
      ready_cell_count: Number(derived.ready_cell_count ?? 0),
      eligible_cell_count: typeof derived.eligible_cell_count === 'number'
        ? Number(derived.eligible_cell_count)
        : undefined,
      max_danger_cell_count: Number(derived.max_danger_cell_count ?? 0),
      selected_level_cell_count: typeof derived.selected_level_cell_count === 'number'
        ? Number(derived.selected_level_cell_count)
        : undefined,
      selected_level_cell_share: typeof derived.selected_level_cell_share === 'number'
        ? Number(derived.selected_level_cell_share)
        : undefined,
      problem_counts: normalizeProblemCounts(derived.problem_counts),
    },
  };
}

function normalizePeakWindow(value: unknown): ForecastBulletin['peak_window'] {
  if (!value || typeof value !== 'object' || Array.isArray(value)) return undefined;
  const row = value as Record<string, unknown>;
  if (typeof row.window !== 'string') return undefined;
  return {
    window: row.window,
    danger_level: Number(row.danger_level ?? 0),
    danger_label: typeof row.danger_label === 'string' ? row.danger_label : 'Unknown',
    primary_problem: typeof row.primary_problem === 'string' ? row.primary_problem : 'no_distinct_avalanche_problem',
    forecast_hours: Array.isArray(row.forecast_hours) ? row.forecast_hours.map((hour) => Number(hour)).filter(Number.isFinite) : [],
    local_start: typeof row.local_start === 'string' ? row.local_start : '',
    local_end: typeof row.local_end === 'string' ? row.local_end : '',
    selected_forecast_hour: typeof row.selected_forecast_hour === 'number' ? Number(row.selected_forecast_hour) : undefined,
    selected_hour_local_start: typeof row.selected_hour_local_start === 'string' ? row.selected_hour_local_start : undefined,
    selected_hour_local_end: typeof row.selected_hour_local_end === 'string' ? row.selected_hour_local_end : undefined,
  };
}

function normalizeDaypart(value: unknown): ForecastBulletinDaypart | undefined {
  if (!value || typeof value !== 'object' || Array.isArray(value)) return undefined;
  const row = value as Record<string, unknown>;
  if (typeof row.window !== 'string') return undefined;
  const windowMatch = row.window.match(/^day_(\d+)_(night|morning|afternoon|evening)$/);
  const inferredDayIndex = windowMatch ? Number(windowMatch[1]) : undefined;
  const inferredDaypart = windowMatch?.[2];
  const dangerLevel = Number(row.danger_level ?? 0);
  return {
    window: row.window,
    day_index: typeof row.day_index === 'number' && Number.isFinite(row.day_index)
      ? Number(row.day_index)
      : inferredDayIndex ?? 0,
    daypart: typeof row.daypart === 'string' ? row.daypart : (inferredDaypart ?? 'unknown'),
    danger_level: Number.isFinite(dangerLevel) ? dangerLevel : 0,
    danger_label: typeof row.danger_label === 'string'
      ? row.danger_label
      : (EAWS_DANGER_LABELS[Number.isFinite(dangerLevel) ? dangerLevel : 0] ?? 'Unknown'),
    primary_problem: typeof row.primary_problem === 'string'
      ? row.primary_problem
      : 'no_distinct_avalanche_problem',
    problems: Array.isArray(row.problems) ? row.problems.map(String) : [],
    forecast_hours: Array.isArray(row.forecast_hours)
      ? row.forecast_hours.map((hour) => Number(hour)).filter(Number.isFinite)
      : [],
    local_start: typeof row.local_start === 'string' ? row.local_start : undefined,
    local_end: typeof row.local_end === 'string' ? row.local_end : undefined,
    selected_forecast_hour: typeof row.selected_forecast_hour === 'number'
      ? Number(row.selected_forecast_hour)
      : undefined,
    selected_hour_local_start: typeof row.selected_hour_local_start === 'string'
      ? row.selected_hour_local_start
      : undefined,
    selected_hour_local_end: typeof row.selected_hour_local_end === 'string'
      ? row.selected_hour_local_end
      : undefined,
    daypart_aggregation_mode: typeof row.daypart_aggregation_mode === 'string'
      ? row.daypart_aggregation_mode
      : undefined,
    window_frequency_basis: typeof row.window_frequency_basis === 'string'
      ? row.window_frequency_basis
      : undefined,
  };
}

function normalizeProblemCounts(value: unknown): Record<string, number> {
  if (!value || typeof value !== 'object' || Array.isArray(value)) return {};
  return Object.fromEntries(
    Object.entries(value as Record<string, unknown>)
      .map(([key, raw]) => [key, Number(raw)] as const)
      .filter(([, numeric]) => Number.isFinite(numeric)),
  );
}

export function formatBulletinProblem(problem: string): string {
  if (!problem) return 'No distinct avalanche problem';
  if (problem === 'no_distinct_avalanche_problem') return 'No distinct avalanche problem';
  return problem
    .split('_')
    .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
    .join(' ');
}

export function formatBulletinProneLocation(bulletin: ForecastBulletin): string | null {
  const aspects = bulletin.critical_aspects.join(', ');
  const { min_m, max_m } = bulletin.critical_elevations;
  const elevation = typeof min_m === 'number' && typeof max_m === 'number'
    ? `${min_m}\u2013${max_m} m`
    : null;
  if (aspects && elevation) return `${aspects} • ${elevation}`;
  return aspects || elevation || null;
}

export function getDaypartSortIndex(daypart: string): number {
  const index = BULLETIN_DAYPART_ORDER.indexOf(daypart as typeof BULLETIN_DAYPART_ORDER[number]);
  return index === -1 ? BULLETIN_DAYPART_ORDER.length : index;
}

export function formatBulletinDaypartLabel(daypart: string): string {
  if (!daypart) return 'Unknown';
  return daypart.charAt(0).toUpperCase() + daypart.slice(1);
}

export function formatBulletinWindowLabel(window: string): string {
  if (!window) return 'Unknown window';
  const match = window.match(/^day_(\d+)_(night|morning|afternoon|evening)$/);
  if (!match) return window.replace(/_/g, ' ');
  return `Day ${match[1]} ${formatBulletinDaypartLabel(match[2])}`;
}
