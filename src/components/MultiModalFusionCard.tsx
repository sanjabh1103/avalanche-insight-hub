import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Layers, AlertTriangle } from 'lucide-react';
import { FUSION_SOURCES, RISK_LABELS } from '@/lib/constants';
import { selectRiskDrivers } from '@/lib/riskNarratives';
import { getRiskColor, type GridCell } from '@/lib/gridUtils';

interface Props {
  selectedCell: GridCell | null;
}

function StatusDot({ state }: { state: 'good' | 'warn' | 'bad' | 'none' }) {
  const color =
    state === 'good' ? 'bg-emerald-500'
    : state === 'warn' ? 'bg-amber-500'
    : state === 'bad' ? 'bg-red-500'
    : 'bg-slate-500';
  return (
    <span className="relative flex h-1.5 w-1.5">
      <span className={`relative inline-flex rounded-full h-1.5 w-1.5 ${color}`} />
    </span>
  );
}

function SourceRow({
  label,
  provenance,
  state,
  children,
}: {
  label: string;
  provenance: string;
  state: 'good' | 'warn' | 'bad' | 'none';
  children: React.ReactNode;
}) {
  return (
    <div className="flex items-start gap-2 py-1.5 border-b border-border/40 last:border-0">
      <div className="mt-1.5"><StatusDot state={state} /></div>
      <div className="flex-1 min-w-0">
        <div className="flex items-center justify-between gap-2">
          <span className="text-[10px] font-semibold uppercase tracking-[0.18em] text-muted-foreground">{label}</span>
          <span className="text-[8px] font-mono text-muted-foreground/70">{provenance}</span>
        </div>
        <div className="mt-0.5">{children}</div>
      </div>
    </div>
  );
}

export default function MultiModalFusionCard({ selectedCell }: Props) {
  if (!selectedCell) {
    return (
      <Card className="border border-border/70 bg-card/60 backdrop-blur-xl">
        <CardHeader className="p-3 pb-1">
          <CardTitle className="text-xs uppercase tracking-[0.24em] text-muted-foreground flex items-center gap-1.5">
            <Layers className="h-3 w-3" /> Fusion View
          </CardTitle>
        </CardHeader>
        <CardContent className="p-3 pt-2">
          <p className="text-xs italic text-muted-foreground">Select a cell to view fused multi-source data.</p>
        </CardContent>
      </Card>
    );
  }

  const { drivers: shapData } = selectRiskDrivers(selectedCell);
  const top3 = shapData.slice(0, 3);
  const maxShap = Math.max(...top3.map((d) => Math.abs(d.value)), 0.01);

  const coverageState = selectedCell.coverageFlags?.sar_coverage_state;
  const sarState: 'good' | 'warn' | 'bad' | 'none' =
    coverageState === 'good' || coverageState === 'full_coverage' ? 'good'
    : coverageState === 'low' || coverageState === 'low_coverage' ? 'warn'
    : 'none';

  const seismic = selectedCell.seismicAmplification;
  const seismicState: 'good' | 'warn' | 'bad' | 'none' = seismic ? 'warn' : 'none';

  const proxy = selectedCell.snowpackProxy;
  const snowpackState: 'good' | 'warn' | 'bad' | 'none' =
    proxy && typeof proxy.estimated_shear_strength === 'number' ? 'good' : 'none';

  const prob = selectedCell.probability ?? selectedCell.riskScore / 5;
  const riskScore = selectedCell.riskScore;

  return (
    <Card className="border border-border/70 bg-card/60 backdrop-blur-xl">
      <CardHeader className="p-3 pb-1">
        <CardTitle className="text-xs uppercase tracking-[0.24em] text-muted-foreground flex items-center gap-1.5">
          <Layers className="h-3 w-3" /> Fusion View
          <Badge className="bg-sky-500/15 text-sky-300 border-0 text-[8px] px-1.5 py-0 rounded-full">
            ● MULTI-SOURCE
          </Badge>
        </CardTitle>
      </CardHeader>
      <CardContent className="p-3 pt-1">
        {/* Row 1: governed reference output; deep-learning candidates remain shadow-only. */}
        <SourceRow label="RF/TreeSHAP reference" provenance="Calibrated RF + TreeSHAP" state={riskScore >= 4 ? 'bad' : riskScore >= 3 ? 'warn' : 'good'}>
          <div className="flex items-center gap-2">
            <Badge
              className="text-[9px] font-mono rounded-full border-0"
              style={{ backgroundColor: getRiskColor(riskScore), color: '#000' }}
            >
              {riskScore} — {RISK_LABELS[riskScore]}
            </Badge>
            <span className="text-[10px] font-mono text-muted-foreground">
              p={prob.toFixed(2)}
            </span>
          </div>
        </SourceRow>

        {/* Row 2: SHAP Top-3 */}
        <SourceRow label="SHAP Top-3" provenance="TreeSHAP" state={top3.length > 0 ? 'good' : 'none'}>
          {top3.length === 0 ? (
            <span className="text-[10px] text-muted-foreground">—</span>
          ) : (
            <div className="space-y-1">
              {top3.map((d) => {
                const magnitude = Math.abs(d.value);
                const width = `${(magnitude / maxShap) * 100}%`;
                const positiveRisk = d.value >= 0;
                return (
                  <div key={d.feature} className="flex items-center gap-1.5">
                    <span className="text-[8px] text-secondary-foreground w-14 text-right truncate font-mono">
                      {d.label}
                    </span>
                    <div className="flex-1 h-2.5 bg-black/20 rounded-full overflow-hidden">
                      <div
                        className="h-full rounded-full transition-all duration-300"
                        style={{ width, backgroundColor: positiveRisk ? 'hsl(8, 85%, 55%)' : 'hsl(156, 70%, 45%)' }}
                      />
                    </div>
                    <span className="text-[8px] font-mono text-muted-foreground w-8 text-right">
                      {d.value >= 0 ? '+' : ''}{d.value.toFixed(3)}
                    </span>
                  </div>
                );
              })}
            </div>
          )}
        </SourceRow>

        {/* Row 3: SAR Coverage */}
        <SourceRow label="SAR Coverage" provenance="Sentinel-1" state={sarState}>
          <span className="text-[10px] font-mono text-muted-foreground">
            {coverageState ? coverageState.replace(/_/g, ' ') : 'unavailable'}
          </span>
        </SourceRow>

        {/* Row 4: Snowpack */}
        <SourceRow label="Snowpack" provenance={FUSION_SOURCES.snowpack.provenance} state={snowpackState}>
          {proxy && typeof proxy.estimated_shear_strength === 'number' ? (
            <div className="flex items-center gap-3 text-[10px] font-mono text-muted-foreground">
              <span>shear {proxy.estimated_shear_strength.toFixed(1)} kPa</span>
              <span>settle {proxy.snow_settlement_index?.toFixed(2) ?? '—'}</span>
            </div>
          ) : (
            <span className="text-[10px] text-muted-foreground">—</span>
          )}
        </SourceRow>

        {/* Row 5: Seismic */}
        <SourceRow label="Seismic" provenance="USGS" state={seismicState}>
          {seismic ? (
            <div className="flex items-center gap-2 text-[10px] font-mono">
              <span className="text-amber-300">{seismic.factor.toFixed(2)}x</span>
              <span className="text-muted-foreground">M{seismic.magnitude.toFixed(1)}</span>
              <span className="text-muted-foreground">{seismic.hours_since_event.toFixed(1)}h ago</span>
              <span className="text-muted-foreground">phase {seismic.window_phase}</span>
            </div>
          ) : (
            <span className="text-[10px] text-muted-foreground">no active event</span>
          )}
        </SourceRow>

        {/* Wave D: Anomaly badge row */}
        {selectedCell.verificationPacket && (
          <SourceRow
            label="Anomaly"
            provenance="Verification Spine"
            state={
              selectedCell.verificationPacket.anomaly_state === 'anomaly' ? 'bad'
              : selectedCell.verificationPacket.anomaly_state === 'watch' ? 'warn'
              : selectedCell.verificationPacket.anomaly_state === 'normal' ? 'good'
              : 'none'
            }
          >
            <div className="flex items-center gap-2">
              {selectedCell.verificationPacket.anomaly_state && (
                <Badge
                  className="text-[9px] rounded-full border-0"
                  variant="outline"
                >
                  {selectedCell.verificationPacket.anomaly_state.toUpperCase()}
                </Badge>
              )}
              {selectedCell.verificationPacket.residual_zscore !== undefined && (
                <span className="text-[10px] font-mono text-muted-foreground">
                  z={selectedCell.verificationPacket.residual_zscore.toFixed(2)}
                </span>
              )}
              {selectedCell.verificationPacket.attribution_bucket && (
                <span className="text-[9px] text-muted-foreground/70">
                  {selectedCell.verificationPacket.attribution_bucket.replace(/_/g, ' ')}
                </span>
              )}
            </div>
            {selectedCell.discrepancyReasons && selectedCell.discrepancyReasons.length > 0 && (
              <div className="mt-0.5 flex flex-wrap gap-1">
                {selectedCell.discrepancyReasons.map((reason, i) => (
                  <span key={i} className="text-[8px] text-muted-foreground/60 bg-muted/30 px-1 rounded">
                    {reason}
                  </span>
                ))}
              </div>
            )}
          </SourceRow>
        )}

        {/* Wave D: Consensus gauge row */}
        {selectedCell.fusionEvidence && (
          <SourceRow
            label="Consensus"
            provenance="Fusion Engine"
            state={
              (selectedCell.fusionEvidence.consensus_score ?? 0) >= 0.7 ? 'good'
              : (selectedCell.fusionEvidence.consensus_score ?? 0) >= 0.4 ? 'warn'
              : 'bad'
            }
          >
            <div className="flex items-center gap-2">
              <div className="flex-1 h-2 bg-black/20 rounded-full overflow-hidden">
                <div
                  className="h-full rounded-full transition-all duration-300"
                  style={{
                    width: `${(selectedCell.fusionEvidence.consensus_score ?? 0) * 100}%`,
                    backgroundColor:
                      (selectedCell.fusionEvidence.consensus_score ?? 0) >= 0.7
                        ? 'hsl(156, 70%, 45%)'
                        : (selectedCell.fusionEvidence.consensus_score ?? 0) >= 0.4
                        ? 'hsl(45, 90%, 55%)'
                        : 'hsl(8, 85%, 55%)',
                  }}
                />
              </div>
              <span className="text-[10px] font-mono text-muted-foreground">
                {((selectedCell.fusionEvidence.consensus_score ?? 0) * 100).toFixed(0)}%
              </span>
            </div>
            {selectedCell.fusionEvidence.contributing_sensors && selectedCell.fusionEvidence.contributing_sensors.length > 0 && (
              <div className="mt-0.5 flex flex-wrap gap-1">
                {selectedCell.fusionEvidence.contributing_sensors.map((sensor, i) => (
                  <span key={i} className="text-[8px] text-muted-foreground/60">
                    {sensor}
                  </span>
                ))}
              </div>
            )}
          </SourceRow>
        )}

        {/* Wave D: Baseline-deviation row */}
        {selectedCell.verificationPacket && selectedCell.verificationPacket.observed !== undefined && selectedCell.verificationPacket.baseline_p50 !== undefined && (
          <SourceRow
            label="Baseline Δ"
            provenance="Rolling Stats"
            state={
              Math.abs(selectedCell.verificationPacket.residual_zscore ?? 0) > 2 ? 'bad'
              : Math.abs(selectedCell.verificationPacket.residual_zscore ?? 0) > 1 ? 'warn'
              : 'good'
            }
          >
            <div className="flex items-center gap-2 text-[10px] font-mono text-muted-foreground">
              <span>obs {selectedCell.verificationPacket.observed!.toFixed(2)}</span>
              <span>p50 {selectedCell.verificationPacket.baseline_p50!.toFixed(2)}</span>
              <span className={
                Math.abs(selectedCell.verificationPacket.residual_zscore ?? 0) > 2
                  ? 'text-red-400'
                  : Math.abs(selectedCell.verificationPacket.residual_zscore ?? 0) > 1
                  ? 'text-amber-400'
                  : 'text-emerald-400'
              }>
                Δ {(selectedCell.verificationPacket.observed! - selectedCell.verificationPacket.baseline_p50!).toFixed(2)}
              </span>
            </div>
          </SourceRow>
        )}

        {/* Permanent disclaimer */}
        <div className="flex items-center gap-1 pt-1.5 border-t border-border/40">
          <AlertTriangle className="h-2.5 w-2.5 text-muted-foreground/50" />
          <span className="text-[8px] italic text-muted-foreground/60">
            Decision-support only. Not an official avalanche warning.
          </span>
        </div>
      </CardContent>
    </Card>
  );
}
