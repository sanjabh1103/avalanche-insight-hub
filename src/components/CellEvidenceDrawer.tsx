import { useEffect, useMemo, useState } from 'react';
import { FilePlus2, ShieldCheck, Snowflake, Waypoints, Cpu, FlaskConical } from 'lucide-react';
import BaselineTimeseriesChart from '@/components/BaselineTimeseriesChart';
import { toast } from 'sonner';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import type { GridCell } from '@/lib/gridUtils';
import {
  buildCellValidationCaseInput,
  createScientistValidationCase,
  fetchCellEvidenceLinks,
  type CellEvidenceLinks,
} from '@/lib/scientistValidation';
import {
  buildRiskExplanation,
  selectRiskDrivers,
  buildPhysicsExplanation,
  physicsStabilityLabel,
  physicsShearLabel,
  PHYSICS_GRAIN_LABELS,
} from '@/lib/riskNarratives';
import { SEISMIC_WINDOW_LABELS } from '@/lib/constants';

interface Props {
  selectedCell: GridCell | null;
  regionKey?: string | null;
  regionName?: string | null;
  forecastRunId?: string | null;
  forecastGridId?: string | null;
  forecastHour?: number | null;
  modelMetadata?: Record<string, unknown> | null;
}

function formatNumber(value: number | null | undefined, digits = 2): string {
  return typeof value === 'number' && Number.isFinite(value) ? value.toFixed(digits) : 'n/a';
}

function evidenceBadgeTone(value: string | null | undefined): string {
  if (value === 'tree_shap' || value === 'ready' || value === 'available') return 'bg-emerald-500/15 text-emerald-300';
  if (value === 'heuristic_fallback' || value === 'high') return 'bg-amber-500/15 text-amber-300';
  if (value === 'unavailable' || value === 'blocked') return 'bg-red-500/15 text-red-300';
  return 'bg-sky-500/15 text-sky-300';
}

export default function CellEvidenceDrawer({
  selectedCell,
  regionKey,
  regionName,
  forecastRunId,
  forecastGridId,
  forecastHour,
  modelMetadata,
}: Props) {
  const [queueing, setQueueing] = useState(false);
  const [linkedEvidence, setLinkedEvidence] = useState<CellEvidenceLinks>({ outcomes: [], field_reports: [] });
  const [linkedEvidenceStatus, setLinkedEvidenceStatus] = useState<'idle' | 'loading' | 'loaded' | 'error'>('idle');

  const caseInput = useMemo(() => {
    if (!selectedCell) return null;
    return buildCellValidationCaseInput({
      selectedCell,
      regionKey,
      regionName,
      forecastRunId,
      forecastGridId,
      forecastHour,
      modelMetadata,
    });
  }, [forecastGridId, forecastHour, forecastRunId, modelMetadata, regionKey, regionName, selectedCell]);

  useEffect(() => {
    if (!selectedCell) {
      setLinkedEvidence({ outcomes: [], field_reports: [] });
      setLinkedEvidenceStatus('idle');
      return;
    }
    let cancelled = false;
    setLinkedEvidenceStatus('loading');
    fetchCellEvidenceLinks({
      regionKey,
      forecastRunId,
      forecastGridId,
      cellRow: selectedCell.row,
      cellCol: selectedCell.col,
    })
      .then((links) => {
        if (!cancelled) {
          setLinkedEvidence(links);
          setLinkedEvidenceStatus('loaded');
        }
      })
      .catch(() => {
        if (!cancelled) {
          setLinkedEvidence({ outcomes: [], field_reports: [] });
          setLinkedEvidenceStatus('error');
        }
      });
    return () => {
      cancelled = true;
    };
  }, [forecastGridId, forecastRunId, regionKey, selectedCell]);

  const queueCase = async () => {
    if (!caseInput) return;
    setQueueing(true);
    try {
      const created = await createScientistValidationCase({
        ...caseInput,
        evidence: {
          ...caseInput.evidence,
          forecast_outcomes: linkedEvidence.outcomes,
          field_reports: linkedEvidence.field_reports,
          snowpack_proxy: selectedCell?.snowpackProxy ?? null,
        },
      });
      toast.success(`Queued scientist validation case ${created.id.slice(0, 8)}`);
    } catch (error) {
      toast.error(error instanceof Error ? error.message : 'Failed to queue validation case');
    } finally {
      setQueueing(false);
    }
  };

  return (
    <Card className="border border-border/70 bg-card/60 backdrop-blur-xl">
      <CardHeader className="p-3 pb-1">
        <CardTitle className="flex items-center gap-1.5 text-xs uppercase tracking-[0.24em] text-muted-foreground">
          <ShieldCheck className="h-3 w-3" />
          Cell Evidence
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-3 p-3 pt-2">
        {!selectedCell ? (
          <p className="text-xs italic text-muted-foreground">
            Select a forecast cell to inspect validation evidence and queue scientist review.
          </p>
        ) : (
          <>
            <div className="flex flex-wrap items-center gap-1.5">
              <Badge className="rounded-full border-0 bg-sky-500/15 text-sky-300">
                r{selectedCell.row} c{selectedCell.col}
              </Badge>
              <Badge className={`rounded-full border-0 ${evidenceBadgeTone(selectedCell.uncertaintyClass)}`}>
                uncertainty {selectedCell.uncertaintyClass ?? 'n/a'}
              </Badge>
              <Badge className={`rounded-full border-0 ${evidenceBadgeTone(selectedCell.explainabilityMode)}`}>
                {selectedCell.explainabilityMode ?? 'explanation n/a'}
              </Badge>
            </div>

            <div className="grid grid-cols-2 gap-x-3 gap-y-1 text-[10px]">
              <div className="text-muted-foreground">Risk score</div>
              <div className="text-right font-mono text-foreground">{selectedCell.riskScore}/5</div>
              <div className="text-muted-foreground">Probability</div>
              <div className="text-right font-mono text-foreground">{formatNumber(selectedCell.probability)}</div>
              <div className="text-muted-foreground">Uncertainty span</div>
              <div className="text-right font-mono text-foreground">{formatNumber(selectedCell.uncertaintySpan)}</div>
              <div className="text-muted-foreground">Dominant driver</div>
              <div className="text-right font-mono text-foreground">{selectedCell.dominantDriverFeature ?? 'n/a'}</div>
              <div className="text-muted-foreground">Runout seed</div>
              <div className="text-right font-mono text-foreground">{selectedCell.runoutSeed ? 'yes' : 'no'}</div>
              <div className="text-muted-foreground">Public mask</div>
              <div className="text-right font-mono text-foreground">
                {selectedCell.publicEligible === false ? 'withheld' : 'eligible'}
              </div>
            </div>

            {/* F18: Dual-Narrative Explainability — ML Narrative card */}
            <div className="rounded-lg border border-border/60 bg-black/10 p-2.5 space-y-2">
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-1.5 font-semibold uppercase tracking-[0.18em] text-[10px]">
                  <Cpu className="h-3 w-3" />
                  ML Explanation
                </div>
                <Badge className={`text-[8px] rounded-full border-0 px-1.5 py-0 ${evidenceBadgeTone(selectedCell.explainabilityMode)}`}>
                  {selectedCell.explainabilityMode ?? 'n/a'}
                </Badge>
              </div>
              {(() => {
                const { drivers } = selectRiskDrivers(selectedCell);
                if (drivers.length === 0) {
                  return <p className="text-[10px] text-muted-foreground">SHAP contributions unavailable for this cell.</p>;
                }
                const maxShap = Math.max(...drivers.map((d) => Math.abs(d.value)), 0.01);
                return (
                  <>
                    <div className="space-y-1">
                      {drivers.slice(0, 5).map((d) => {
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
                    <p className="text-[10px] leading-relaxed text-foreground/80">
                      {buildRiskExplanation(selectedCell)}
                    </p>
                  </>
                );
              })()}
            </div>

            {/* F18: Dual-Narrative Explainability — Physics Narrative card */}
            <div className="rounded-lg border border-border/60 bg-black/10 p-2.5 space-y-2">
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-1.5 font-semibold uppercase tracking-[0.18em] text-[10px]">
                  <FlaskConical className="h-3 w-3" />
                  Physics Narrative
                </div>
                <Badge className={`text-[8px] rounded-full border-0 px-1.5 py-0 ${
                  selectedCell.physicsNarrative?.method === 'cosipy_v2' || selectedCell.physicsNarrative?.method === 'snowpack_native'
                    ? 'bg-emerald-500/15 text-emerald-300'
                    : selectedCell.physicsNarrative?.method === 'heuristic_fallback'
                      ? 'bg-amber-500/15 text-amber-300'
                      : 'bg-red-500/15 text-red-300'
                }`}>
                  {selectedCell.physicsNarrative?.method ?? 'unavailable'}
                </Badge>
              </div>
              {selectedCell.physicsNarrative ? (
                <>
                  <div className="grid grid-cols-2 gap-x-3 gap-y-1 text-[10px]">
                    <div className="text-muted-foreground">Shear strength</div>
                    <div className="text-right font-mono">
                      <span className={physicsShearLabel(selectedCell.physicsNarrative.shear_strength_kpa).tone}>
                        {formatNumber(selectedCell.physicsNarrative.shear_strength_kpa, 1)} kPa
                        {' '}
                        ({physicsShearLabel(selectedCell.physicsNarrative.shear_strength_kpa).label})
                      </span>
                    </div>
                    <div className="text-muted-foreground">Stability index</div>
                    <div className="text-right font-mono">
                      <span className={physicsStabilityLabel(selectedCell.physicsNarrative.stability_index).tone}>
                        {formatNumber(selectedCell.physicsNarrative.stability_index)}
                        {' '}
                        ({physicsStabilityLabel(selectedCell.physicsNarrative.stability_index).label})
                      </span>
                    </div>
                    <div className="text-muted-foreground">Grain type</div>
                    <div className="text-right font-mono text-foreground">
                      {PHYSICS_GRAIN_LABELS[selectedCell.physicsNarrative.grain_type ?? ''] ?? selectedCell.physicsNarrative.grain_type ?? '—'}
                    </div>
                    <div className="text-muted-foreground">Temp gradient</div>
                    <div className="text-right font-mono text-foreground">
                      {formatNumber(selectedCell.physicsNarrative.temperature_gradient_per_m, 3)} K/m
                    </div>
                    <div className="text-muted-foreground">Snow height</div>
                    <div className="text-right font-mono text-foreground">
                      {formatNumber(selectedCell.physicsNarrative.snow_height_m, 2)} m
                    </div>
                    <div className="text-muted-foreground">LWC</div>
                    <div className="text-right font-mono text-foreground">
                      {formatNumber(selectedCell.physicsNarrative.liquid_water_content_pct, 1)}%
                    </div>
                  </div>
                  <p className="text-[10px] leading-relaxed text-foreground/80">
                    {buildPhysicsExplanation(selectedCell)}
                  </p>
                  {selectedCell.physicsNarrative.seismic_summary && (
                    <div className="rounded-md border border-amber-400/30 bg-amber-500/10 px-2 py-1.5 text-[10px] text-amber-200">
                      <div className="flex items-center gap-1.5 font-semibold uppercase tracking-[0.14em] mb-0.5">
                        <Snowflake className="h-2.5 w-2.5" />
                        Seismic Cascade
                      </div>
                      {selectedCell.physicsNarrative.seismic_summary}
                      {selectedCell.seismicAmplification && (
                        <div className="mt-0.5 text-[9px] text-amber-300/80">
                          {SEISMIC_WINDOW_LABELS[selectedCell.seismicAmplification.window_phase] ?? `Phase ${selectedCell.seismicAmplification.window_phase}`}
                        </div>
                      )}
                    </div>
                  )}
                </>
              ) : (
                <p className="text-[10px] text-muted-foreground italic">
                  Physics narrative unavailable for this forecast batch. Run a new inference job to populate.
                </p>
              )}
            </div>

            {/* Wave D: Verification packet */}
            {selectedCell.verificationPacket && (
              <div className="rounded-lg border border-border/60 bg-black/10 p-2 text-[10px] text-muted-foreground space-y-1.5">
                <div className="flex items-center gap-1.5 font-semibold uppercase tracking-[0.18em]">
                  <ShieldCheck className="h-3 w-3" />
                  Verification Packet
                </div>
                <div className="grid grid-cols-2 gap-x-3 gap-y-0.5">
                  <div>State</div>
                  <div className="text-right font-mono">
                    <Badge className={`text-[8px] border-0 ${
                      selectedCell.verificationPacket.anomaly_state === 'anomaly' ? 'bg-red-500/15 text-red-300'
                      : selectedCell.verificationPacket.anomaly_state === 'watch' ? 'bg-amber-500/15 text-amber-300'
                      : selectedCell.verificationPacket.anomaly_state === 'normal' ? 'bg-emerald-500/15 text-emerald-300'
                      : 'bg-slate-500/15 text-slate-300'
                    }`}>
                      {selectedCell.verificationPacket.anomaly_state ?? 'unverified'}
                    </Badge>
                  </div>
                  {selectedCell.verificationPacket.residual_zscore !== undefined && (
                    <>
                      <div>Z-score</div>
                      <div className="text-right font-mono">{selectedCell.verificationPacket.residual_zscore.toFixed(2)}</div>
                    </>
                  )}
                  {selectedCell.verificationPacket.attribution_bucket && (
                    <>
                      <div>Attribution</div>
                      <div className="text-right font-mono">
                        {selectedCell.verificationPacket.attribution_bucket.replace(/_/g, ' ')}
                      </div>
                    </>
                  )}
                  {selectedCell.verificationPacket.confidence !== undefined && (
                    <>
                      <div>Confidence</div>
                      <div className="text-right font-mono">{selectedCell.verificationPacket.confidence.toFixed(2)}</div>
                    </>
                  )}
                  {selectedCell.verificationPacket.packet_version && (
                    <>
                      <div>Version</div>
                      <div className="text-right font-mono">{selectedCell.verificationPacket.packet_version}</div>
                    </>
                  )}
                </div>
                {selectedCell.verificationPacket.contributing_sensors && selectedCell.verificationPacket.contributing_sensors.length > 0 && (
                  <div className="flex flex-wrap gap-1 pt-0.5">
                    {selectedCell.verificationPacket.contributing_sensors.map((s, i) => (
                      <span key={i} className="text-[8px] bg-muted/30 px-1 rounded">{s}</span>
                    ))}
                  </div>
                )}
                {selectedCell.discrepancyReasons && selectedCell.discrepancyReasons.length > 0 && (
                  <div className="pt-0.5">
                    <div className="text-[9px] font-semibold uppercase tracking-[0.14em] mb-0.5">Discrepancy reasons</div>
                    {selectedCell.discrepancyReasons.map((r, i) => (
                      <div key={i} className="text-[9px] text-muted-foreground/80">• {r}</div>
                    ))}
                  </div>
                )}
                {selectedCell.verificationPacket.source_freshness_hours &&
                  Object.keys(selectedCell.verificationPacket.source_freshness_hours).length > 0 && (
                  <div className="pt-0.5 border-t border-border/30">
                    <div className="text-[9px] font-semibold uppercase tracking-[0.14em] mb-0.5">Source freshness</div>
                    {Object.entries(selectedCell.verificationPacket.source_freshness_hours).map(([sensor, hours]) => (
                      <div key={sensor} className="flex items-center justify-between text-[9px]">
                        <span className="text-muted-foreground">{sensor}</span>
                        <span className={`font-mono ${hours > 72 ? 'text-red-300/80' : hours > 24 ? 'text-amber-300/80' : 'text-emerald-300/80'}`}>
                          {hours.toFixed(1)}h
                        </span>
                      </div>
                    ))}
                  </div>
                )}
                {selectedCell.verificationPacket.evidence_refs && selectedCell.verificationPacket.evidence_refs.length > 0 && (
                  <div className="pt-0.5 border-t border-border/30">
                    <div className="text-[9px] font-semibold uppercase tracking-[0.14em] mb-0.5">Evidence refs</div>
                    {selectedCell.verificationPacket.evidence_refs.map((ref, i) => (
                      <div key={i} className="text-[8px] font-mono text-muted-foreground/70 truncate" title={ref}>{ref}</div>
                    ))}
                  </div>
                )}
                {selectedCell.verificationPacket.baseline_ids && selectedCell.verificationPacket.baseline_ids.length > 0 && (
                  <div className="pt-0.5 flex flex-wrap gap-1">
                    <span className="text-[9px] font-semibold uppercase tracking-[0.14em]">Baselines:</span>
                    {selectedCell.verificationPacket.baseline_ids.map((id, i) => (
                      <span key={i} className="text-[8px] bg-muted/30 px-1 rounded font-mono">{id}</span>
                    ))}
                  </div>
                )}
                {selectedCell.verificationPacket.lineage &&
                  typeof selectedCell.verificationPacket.lineage === 'object' &&
                  Object.keys(selectedCell.verificationPacket.lineage).length > 0 && (
                  <div className="pt-0.5 border-t border-border/30">
                    <div className="text-[9px] font-semibold uppercase tracking-[0.14em] mb-0.5">Lineage</div>
                    {(() => {
                      const lineage = selectedCell.verificationPacket!.lineage as Record<string, unknown>;
                      const sourceLineage = lineage.source_lineage;
                      if (sourceLineage && typeof sourceLineage === 'object' && !Array.isArray(sourceLineage)) {
                        return Object.entries(sourceLineage).map(([source, info]) => {
                          const infoObj = info as Record<string, unknown>;
                          return (
                            <div key={source} className="text-[9px] space-y-0.5">
                              <span className="text-muted-foreground font-medium">{source}</span>
                              {infoObj.reference && (
                                <span className="text-muted-foreground/60 font-mono ml-1.5 text-[8px]">{String(infoObj.reference)}</span>
                              )}
                              {infoObj.verified !== undefined && (
                                <span className={`ml-1.5 text-[8px] ${infoObj.verified ? 'text-emerald-300/70' : 'text-red-300/70'}`}>
                                  {infoObj.verified ? '✓ verified' : '✗ unverified'}
                                </span>
                              )}
                            </div>
                          );
                        });
                      }
                      return <div className="text-[9px] text-muted-foreground/60 italic">Lineage data available</div>;
                    })()}
                  </div>
                )}
              </div>
            )}

            {selectedCell.verificationPacket &&
              (selectedCell.verificationPacket.baseline_p25 !== undefined ||
               selectedCell.verificationPacket.baseline_p50 !== undefined ||
               selectedCell.verificationPacket.observed !== undefined) && (
              <BaselineTimeseriesChart
                points={[{
                  date: new Date().toISOString().slice(0, 10),
                  p25: selectedCell.verificationPacket.baseline_p25,
                  p50: selectedCell.verificationPacket.baseline_p50,
                  p75: selectedCell.verificationPacket.baseline_p75,
                  observed: selectedCell.verificationPacket.observed,
                  residual_zscore: selectedCell.verificationPacket.residual_zscore,
                  anomaly_state: selectedCell.verificationPacket.anomaly_state,
                }]}
                sensor={selectedCell.verificationPacket.contributing_sensors?.[0]}
              />
            )}

            {/* Wave D: Fusion evidence */}
            {selectedCell.fusionEvidence && (
              <div className="rounded-lg border border-border/60 bg-black/10 p-2 text-[10px] text-muted-foreground space-y-1">
                <div className="flex items-center gap-1.5 font-semibold uppercase tracking-[0.18em]">
                  <Snowflake className="h-3 w-3" />
                  Fusion Evidence
                </div>
                <div className="grid grid-cols-2 gap-x-3 gap-y-0.5">
                  {selectedCell.fusionEvidence.snow_depth_m !== null && selectedCell.fusionEvidence.snow_depth_m !== undefined && (
                    <>
                      <div>Snow depth</div>
                      <div className="text-right font-mono">{selectedCell.fusionEvidence.snow_depth_m.toFixed(2)} m</div>
                    </>
                  )}
                  {selectedCell.fusionEvidence.snow_cover_fraction !== null && selectedCell.fusionEvidence.snow_cover_fraction !== undefined && (
                    <>
                      <div>Snow cover</div>
                      <div className="text-right font-mono">{(selectedCell.fusionEvidence.snow_cover_fraction * 100).toFixed(0)}%</div>
                    </>
                  )}
                  {selectedCell.fusionEvidence.uncertainty !== null && selectedCell.fusionEvidence.uncertainty !== undefined && (
                    <>
                      <div>Uncertainty</div>
                      <div className="text-right font-mono">±{selectedCell.fusionEvidence.uncertainty.toFixed(2)} m</div>
                    </>
                  )}
                  <div>Consensus</div>
                  <div className="text-right font-mono">{((selectedCell.fusionEvidence.consensus_score ?? 0) * 100).toFixed(0)}%</div>
                </div>
              </div>
            )}

            <div className="rounded-lg border border-border/60 bg-black/10 p-2 text-[10px] text-muted-foreground">
              <div className="mb-1 flex items-center gap-1.5 font-semibold uppercase tracking-[0.18em]">
                <Waypoints className="h-3 w-3" />
                Linked reality evidence
              </div>
              <div>
                Forecast outcomes {linkedEvidenceStatus === 'loading' ? 'loading' : linkedEvidence.outcomes.length} · field reports {linkedEvidenceStatus === 'loading' ? 'loading' : linkedEvidence.field_reports.length}
              </div>
              <div className="mt-1">{caseInput?.summary}</div>
              {selectedCell.publicMaskReasons?.length ? (
                <div className="mt-1">Mask reasons: {selectedCell.publicMaskReasons.join(', ')}</div>
              ) : null}
              {linkedEvidenceStatus === 'error' ? (
                <div className="mt-1 text-amber-300">Linked evidence lookup unavailable; queue will still include the cell snapshot.</div>
              ) : null}
            </div>

            <Button
              variant="outline"
              size="sm"
              className="h-8 w-full justify-center gap-2 rounded-2xl border-border/70 bg-black/10 text-[10px] uppercase tracking-[0.16em] hover:bg-white/5"
              onClick={queueCase}
              disabled={queueing}
            >
              <FilePlus2 className="h-3.5 w-3.5" />
              {queueing ? 'Queueing...' : 'Queue For Scientist Review'}
            </Button>
          </>
        )}
      </CardContent>
    </Card>
  );
}
