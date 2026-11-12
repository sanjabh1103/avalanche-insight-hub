import { AlertTriangle } from 'lucide-react';

import { Badge } from '@/components/ui/badge';
import { RISK_COLORS } from '@/lib/constants';
import {
  BULLETIN_DAYPART_ORDER,
  formatBulletinDaypartLabel,
  formatBulletinProblem,
  formatBulletinProneLocation,
  formatBulletinWindowLabel,
  getDaypartSortIndex,
  type ForecastBulletin,
} from '@/lib/forecastBulletins';

interface Props {
  bulletin: ForecastBulletin | null;
  stale?: boolean;
  timeOffset?: number;
  onSelectForecastHour?: (forecastHour: number) => void;
}

function isActiveDaypartWindow(
  timeOffset: number | undefined,
  forecastHours: number[],
  selectedForecastHour?: number,
) {
  if (typeof timeOffset !== 'number') return false;
  if (forecastHours.length > 0) return forecastHours.includes(timeOffset);
  return typeof selectedForecastHour === 'number' ? selectedForecastHour === timeOffset : false;
}

function formatConfidenceReason(reason: string): string {
  switch (reason) {
    case 'partial_coverage':
      return 'Coverage incomplete';
    case 'high_uncertainty_share':
      return 'High uncertainty remains across many eligible cells';
    case 'low_sar_coverage_share':
      return 'SAR support is thin across many eligible cells';
    default:
      return reason.replace(/_/g, ' ');
  }
}

export default function ForecastBulletinBadge({
  bulletin,
  stale = false,
  timeOffset,
  onSelectForecastHour,
}: Props) {
  if (!bulletin) return null;

  const dangerColor = RISK_COLORS[bulletin.danger_level] || '#94a3b8';
  const proneLocation = formatBulletinProneLocation(bulletin);
  const dayOneDayparts = (bulletin.dayparts ?? [])
    .filter((daypart) => daypart.day_index === 1 && BULLETIN_DAYPART_ORDER.includes(daypart.daypart as typeof BULLETIN_DAYPART_ORDER[number]))
    .sort((left, right) => getDaypartSortIndex(left.daypart) - getDaypartSortIndex(right.daypart));
  const peakWindowCaption = bulletin.peak_window?.window && bulletin.peak_window.window !== bulletin.primary_window
    ? `Peak: ${formatBulletinWindowLabel(bulletin.peak_window.window)} • Level ${bulletin.peak_window.danger_level}`
    : null;
  const confidenceCaption = bulletin.confidence_state === 'reduced'
    ? [
      bulletin.confidence_reasons?.[0] ? formatConfidenceReason(bulletin.confidence_reasons[0]) : null,
      bulletin.uncertainty_summary && bulletin.uncertainty_summary.high_uncertainty_cell_count > 0
        ? `High-uncertainty cells ${bulletin.uncertainty_summary.high_uncertainty_cell_count}/${bulletin.uncertainty_summary.eligible_cell_count}`
        : null,
    ].filter(Boolean).join(' • ')
    : null;

  return (
    <div data-testid="forecast-bulletin-root" className="flex min-w-0 w-full flex-1 flex-col items-start gap-3 rounded-2xl border border-border/70 bg-black/20 px-3 py-3 shadow-sm sm:flex-row sm:items-center">
      <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl border border-white/10 bg-white/5">
        <AlertTriangle className="h-4 w-4" style={{ color: dangerColor }} />
      </div>
      <div className="min-w-0 w-full space-y-1">
        <div className="flex min-w-0 flex-wrap items-center gap-2">
          <Badge
            className="rounded-full border-0 text-[11px] font-semibold"
            style={{ backgroundColor: dangerColor, color: '#000' }}
            data-testid="danger-badge"
          >
            {`Danger Level ${bulletin.danger_level}: ${bulletin.danger_label}`}
          </Badge>
          {stale && (
            <Badge className="rounded-full border-0 bg-slate-500/15 text-slate-300 text-[10px] uppercase tracking-[0.18em]">
              Stale
            </Badge>
          )}
          {bulletin.confidence_state === 'reduced' && (
            <Badge
              className="rounded-full border-0 bg-amber-500/20 text-[10px] uppercase tracking-[0.18em] text-amber-200"
              data-testid="confidence-badge"
            >
              Reduced Confidence
            </Badge>
          )}
        </div>
        <div className="text-xs font-medium text-foreground sm:truncate">
          {formatBulletinProblem(bulletin.primary_problem)}
        </div>
        <div className="text-[10px] uppercase tracking-[0.18em] text-muted-foreground sm:truncate">
          {proneLocation ? `${proneLocation} • EAWS-style experimental` : 'EAWS-style experimental'}
        </div>
        {confidenceCaption && (
          <div className="text-[10px] uppercase tracking-[0.16em] text-amber-200/90 sm:truncate" data-testid="confidence-caption">
            {confidenceCaption}
          </div>
        )}
        {dayOneDayparts.length > 0 && (
          <div className="flex min-w-0 flex-wrap items-center gap-1.5 pt-0.5" data-testid="daypart-strip">
            {dayOneDayparts.map((daypart) => {
              const chipColor = RISK_COLORS[daypart.danger_level] || '#94a3b8';
              const isPrimary = daypart.window === bulletin.primary_window;
              const isActive = isActiveDaypartWindow(timeOffset, daypart.forecast_hours, daypart.selected_forecast_hour);
              const canJump = typeof daypart.selected_forecast_hour === 'number';
              return (
                <button
                  type="button"
                  key={daypart.window}
                  data-testid={`daypart-chip-${daypart.daypart}`}
                  data-primary-window={isPrimary ? 'true' : 'false'}
                  data-active-daypart={isActive ? 'true' : 'false'}
                  className="inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-[10px] uppercase tracking-[0.16em] transition-transform hover:-translate-y-px disabled:cursor-default disabled:hover:translate-y-0"
                  style={{
                    borderColor: isActive ? '#f8fafc' : isPrimary ? chipColor : 'rgba(255,255,255,0.12)',
                    backgroundColor: `${chipColor}${isActive ? '42' : isPrimary ? '2e' : '18'}`,
                    color: '#f8fafc',
                    boxShadow: isActive
                      ? `0 0 0 1px rgba(248,250,252,0.95), 0 0 0 2px ${chipColor}`
                      : isPrimary
                        ? `0 0 0 1px ${chipColor}`
                        : undefined,
                  }}
                  disabled={!canJump}
                  onClick={() => {
                    if (typeof daypart.selected_forecast_hour === 'number') {
                      onSelectForecastHour?.(daypart.selected_forecast_hour);
                    }
                  }}
                >
                  <span>{formatBulletinDaypartLabel(daypart.daypart)}</span>
                  <span className="font-semibold">{daypart.danger_level}</span>
                </button>
              );
            })}
          </div>
        )}
        {peakWindowCaption && (
          <div className="text-[10px] uppercase tracking-[0.18em] text-muted-foreground sm:truncate" data-testid="peak-window-caption">
            {peakWindowCaption}
          </div>
        )}
      </div>
    </div>
  );
}
