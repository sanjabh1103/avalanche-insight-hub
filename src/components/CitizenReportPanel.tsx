import { useMemo } from 'react';
import { Users, MapPin } from 'lucide-react';

export interface CitizenReportData {
  report_id: string;
  lat: number;
  lng: number;
  timestamp: string;
  description: string;
  confidence: number;
  status: string;
  hazard_type: string;
  has_photo: boolean;
  estimated_size?: string | null;
}

interface CitizenReportPanelProps {
  reports: CitizenReportData[];
  onSelectReport?: (report: CitizenReportData) => void;
  selectedReportId?: string | null;
}

const STATUS_COLORS: Record<string, string> = {
  pending: '#f59e0b',
  validated: '#22c55e',
  rejected: '#ef4444',
};

export function CitizenReportPanel({
  reports,
  onSelectReport,
  selectedReportId,
}: CitizenReportPanelProps) {
  const sortedReports = useMemo(
    () => [...reports].sort((a, b) => b.timestamp.localeCompare(a.timestamp)),
    [reports],
  );

  if (sortedReports.length === 0) {
    return (
      <div className="rounded-xl border border-border/60 bg-card/50 p-4 text-sm text-muted-foreground">
        No citizen reports yet.
      </div>
    );
  }

  return (
    <div className="rounded-xl border border-border/60 bg-card/50 p-4 space-y-2">
      <div className="flex items-center gap-2">
        <Users className="h-3.5 w-3.5 text-purple-400" />
        <h3 className="text-xs font-mono uppercase tracking-[0.2em] text-muted-foreground">
          Citizen Reports ({sortedReports.length})
        </h3>
      </div>

      <div className="space-y-1.5 max-h-64 overflow-y-auto">
        {sortedReports.map((report) => {
          const statusColor = STATUS_COLORS[report.status] ?? '#6b7280';
          const isSelected = report.report_id === selectedReportId;

          return (
            <button
              key={report.report_id}
              onClick={() => onSelectReport?.(report)}
              className={`flex w-full items-start gap-2 rounded-lg px-3 py-2 text-left transition-colors ${
                isSelected
                  ? 'bg-background/60 ring-1 ring-purple-500/40'
                  : 'bg-background/20 hover:bg-background/40'
              }`}
            >
              <MapPin className="h-3.5 w-3.5 shrink-0 mt-0.5" style={{ color: statusColor }} />
              <div className="min-w-0 flex-1">
                <div className="flex items-center gap-2">
                  <span className="text-xs font-medium text-foreground truncate">
                    {report.hazard_type}
                  </span>
                  <span
                    className="rounded px-1 py-0.5 text-[9px] font-mono font-semibold uppercase"
                    style={{ backgroundColor: `${statusColor}22`, color: statusColor }}
                  >
                    {report.status}
                  </span>
                  {report.has_photo && (
                    <span className="text-[9px] text-muted-foreground">📷</span>
                  )}
                </div>
                <p className="text-[10px] text-muted-foreground line-clamp-2 mt-0.5">
                  {report.description}
                </p>
                <span className="text-[9px] text-muted-foreground/70">
                  {report.lat.toFixed(3)}°, {report.lng.toFixed(3)}°
                </span>
              </div>
            </button>
          );
        })}
      </div>
    </div>
  );
}
