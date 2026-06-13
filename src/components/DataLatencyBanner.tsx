import { Clock, AlertTriangle, CheckCircle } from 'lucide-react';

interface Props {
  /** ISO 8601 timestamp of the last successful forecast batch run */
  lastForecastDate?: string | null;
  /** ISO 8601 timestamp of the last published_at from the forecast_runs table */
  publishedAt?: string | null;
  /** Pre-computed freshness in hours from the API response */
  freshnessHours?: number | null;
}

/**
 * DataLatencyBanner — Surface the real data age to the user.
 *
 * Replaces any implied "same-day freshness" by computing the actual
 * hours since the last successful forecast batch run and displaying
 * a warning when data is older than 24 hours.
 *
 * Thresholds:
 *  - ≤ 12h: green — fresh
 *  - 12–24h: amber — aging
 *  - > 24h: red — stale, explicit warning
 */
export default function DataLatencyBanner({
  lastForecastDate,
  publishedAt,
  freshnessHours,
}: Props) {
  const ageHours = computeAgeHours(lastForecastDate, publishedAt, freshnessHours);

  if (ageHours === null) return null;

  const { label, tone, Icon } = classifyFreshness(ageHours);

  return (
    <div
      data-testid="data-latency-banner"
      className={`flex items-center gap-2 rounded-xl border px-3 py-1.5 text-[11px] leading-tight ${tone}`}
    >
      <Icon className="h-3.5 w-3.5 shrink-0" />
      <span>
        <strong>Data age:</strong> {formatAge(ageHours)} — {label}
      </span>
    </div>
  );
}

function computeAgeHours(
  forecastDate?: string | null,
  publishedAt?: string | null,
  freshnessHours?: number | null,
): number | null {
  // If the API already gave us a freshness number, use it directly
  if (typeof freshnessHours === 'number' && freshnessHours >= 0) return freshnessHours;

  // Fall back to computing from publishedAt or forecastDate
  const reference = publishedAt || forecastDate;
  if (!reference) return null;

  const ts = new Date(reference);
  if (Number.isNaN(ts.getTime())) return null;

  const diffMs = Date.now() - ts.getTime();
  return Math.max(0, diffMs / (1000 * 60 * 60));
}

function classifyFreshness(ageHours: number): {
  label: string;
  tone: string;
  Icon: typeof Clock;
} {
  if (ageHours <= 12) {
    return {
      label: 'Fresh — within same-day batch window',
      tone: 'border-emerald-500/30 bg-emerald-500/8 text-emerald-300',
      Icon: CheckCircle,
    };
  }
  if (ageHours <= 24) {
    return {
      label: 'Aging — batch run may be delayed',
      tone: 'border-amber-500/30 bg-amber-500/10 text-amber-300',
      Icon: Clock,
    };
  }
  return {
    label: 'Stale — last batch run was more than 24 hours ago. Results may not reflect current conditions.',
    tone: 'border-red-500/30 bg-red-500/10 text-red-300',
    Icon: AlertTriangle,
  };
}

function formatAge(hours: number): string {
  if (hours < 1) return '<1 hour';
  if (hours < 48) return `${Math.round(hours)}h`;
  const days = Math.floor(hours / 24);
  const remainingHours = Math.round(hours % 24);
  return `${days}d ${remainingHours}h`;
}
