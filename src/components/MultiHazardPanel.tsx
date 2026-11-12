import { useMemo } from 'react';
import { Mountain, Waves, Zap, AlertTriangle, Activity } from 'lucide-react';

interface HazardAssessmentData {
  hazard_type: string;
  risk_score: number;
  risk_level: number;
  confidence: number;
  trigger_met: boolean;
  contributing_factors: Record<string, number>;
  metadata?: Record<string, unknown>;
}

interface MultiHazardPanelProps {
  assessments: Record<string, HazardAssessmentData>;
  dominantHazard: string;
  compositeRisk: number;
  compositeRiskLevel: number;
  cellLat?: number;
  cellLng?: number;
}

const HAZARD_META: Record<string, { display: string; color: string; icon: typeof Mountain }> = {
  avalanche: { display: 'Avalanche', color: '#2563eb', icon: Mountain },
  landslide: { display: 'Landslide', color: '#d97706', icon: AlertTriangle },
  flood: { display: 'Flood / GLOF', color: '#0891b2', icon: Waves },
  rockfall: { display: 'Rockfall', color: '#dc2626', icon: Zap },
  debris_flow: { display: 'Debris Flow', color: '#9333ea', icon: Activity },
};

const RISK_LABELS = ['None', 'Low', 'Moderate', 'Considerable', 'High', 'Extreme'];

export function MultiHazardPanel({
  assessments,
  dominantHazard,
  compositeRisk,
  compositeRiskLevel,
  cellLat,
  cellLng,
}: MultiHazardPanelProps) {
  const sortedHazards = useMemo(() => {
    return Object.entries(assessments).sort(
      ([, a], [, b]) => b.risk_score - a.risk_score,
    );
  }, [assessments]);

  if (sortedHazards.length === 0) {
    return (
      <div className="rounded-xl border border-border/60 bg-card/50 p-4 text-sm text-muted-foreground">
        No multi-hazard data available for this cell.
      </div>
    );
  }

  return (
    <div className="rounded-xl border border-border/60 bg-card/50 p-4 space-y-3">
      <div className="flex items-center justify-between">
        <h3 className="text-xs font-mono uppercase tracking-[0.2em] text-muted-foreground">
          Multi-Hazard Assessment
        </h3>
        {cellLat != null && cellLng != null && (
          <span className="text-[10px] font-mono text-muted-foreground/70">
            {cellLat.toFixed(3)}°, {cellLng.toFixed(3)}°
          </span>
        )}
      </div>

      {/* Composite risk summary */}
      <div className="flex items-center gap-3 rounded-lg bg-background/40 px-3 py-2">
        <div
          className="h-2 w-2 rounded-full"
          style={{
            backgroundColor: HAZARD_META[dominantHazard]?.color ?? '#6b7280',
          }}
        />
        <span className="text-xs text-muted-foreground">Dominant:</span>
        <span className="text-sm font-semibold text-foreground">
          {HAZARD_META[dominantHazard]?.display ?? dominantHazard}
        </span>
        <span className="ml-auto text-xs text-muted-foreground">
          Composite: <span className="font-mono text-foreground">{compositeRisk.toFixed(2)}</span>
        </span>
        <span
          className="rounded px-1.5 py-0.5 text-[10px] font-mono font-semibold"
          style={{
            backgroundColor: `rgba(${compositeRiskLevel >= 3 ? '220,38,38' : '37,99,235'},0.15)`,
            color: compositeRiskLevel >= 3 ? '#dc2626' : '#2563eb',
          }}
        >
          {RISK_LABELS[compositeRiskLevel] ?? 'Unknown'}
        </span>
      </div>

      {/* Per-hazard bars */}
      <div className="space-y-2">
        {sortedHazards.map(([htype, assessment]) => {
          const meta = HAZARD_META[htype];
          const Icon = meta?.icon ?? AlertTriangle;
          const riskPct = Math.min((assessment.risk_score / 5) * 100, 100);
          const isDominant = htype === dominantHazard;

          return (
            <div
              key={htype}
              className={`rounded-lg px-3 py-2 transition-colors ${
                isDominant ? 'bg-background/60 ring-1 ring-border/40' : 'bg-background/20'
              }`}
            >
              <div className="flex items-center gap-2">
                <Icon
                  className="h-3.5 w-3.5"
                  style={{ color: meta?.color ?? '#6b7280' }}
                />
                <span className="text-xs font-medium text-foreground">
                  {meta?.display ?? htype}
                </span>
                {assessment.trigger_met && (
                  <span className="ml-1 rounded bg-red-500/15 px-1 py-0.5 text-[9px] font-mono font-semibold uppercase text-red-400">
                    Trigger
                  </span>
                )}
                <span className="ml-auto text-[10px] font-mono text-muted-foreground">
                  {assessment.risk_score.toFixed(2)}
                </span>
              </div>

              {/* Risk bar */}
              <div className="mt-1.5 h-1.5 w-full overflow-hidden rounded-full bg-muted/30">
                <div
                  className="h-full rounded-full transition-all duration-300"
                  style={{
                    width: `${riskPct}%`,
                    backgroundColor: meta?.color ?? '#6b7280',
                  }}
                />
              </div>

              {/* Contributing factors */}
              {Object.keys(assessment.contributing_factors).length > 0 && (
                <div className="mt-1.5 flex flex-wrap gap-1">
                  {Object.entries(assessment.contributing_factors)
                    .sort(([, a], [, b]) => b - a)
                    .slice(0, 3)
                    .map(([factor, value]) => (
                      <span
                        key={factor}
                        className="rounded bg-muted/20 px-1 py-0.5 text-[9px] font-mono text-muted-foreground"
                      >
                        {factor}: {(value * 100).toFixed(0)}%
                      </span>
                    ))}
                </div>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}
