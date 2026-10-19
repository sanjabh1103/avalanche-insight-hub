import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Tooltip, TooltipContent, TooltipTrigger } from '@/components/ui/tooltip';
import { RISK_LABELS } from '@/lib/constants';
import {
  getCellMaskLabel,
  getCellMaskReasonDescriptions,
  getCellMaskSummary,
  getRiskColor,
  isCellMasked,
  isCellUnavailable,
  type GridCell,
} from '@/lib/gridUtils';
import { buildRiskExplanation, selectRiskDrivers } from '@/lib/riskNarratives';

function stripUnit(value: string): string {
  return String(value).replace(/\s*(cm|mm|km\/h|m\/s|°C|C|in|ft|mph)\s*$/i, '').trim();
}

function formatWeatherValue(value: string | undefined, unit: string): string {
  if (!value || value === 'N/A' || value === '') return `—`;
  return `${stripUnit(value)} ${unit}`;
}

interface WeatherSummary {
  snowfall_24h: string;
  wind_speed: string;
  temperature: string;
  precipitation: string;
  snow_depth: string;
}

interface Props {
  cell: GridCell | null;
  weatherSummary?: WeatherSummary | null;
  hasForecastData?: boolean;
  forecastAvailability?: 'ready' | 'partial' | 'stale' | 'unavailable';
  forecastNotice?: string | null;
}

function formatCriterionName(value?: string | null): string {
  if (!value) return 'Unknown';
  return value.replace(/_/g, ' ');
}

export default function RiskDashboard({
  cell,
  weatherSummary,
  hasForecastData = true,
  forecastAvailability = 'ready',
  forecastNotice,
}: Props) {
  if (!cell) {
    const emptyTitle = hasForecastData
      ? 'Click a grid tile on the map to inspect risk details'
      : 'Published forecast artifact is not loaded yet';
    const emptyLabel = hasForecastData
      ? 'Telemetry standby'
      : forecastAvailability === 'unavailable'
        ? 'Batch proof unavailable'
        : 'Batch proof pending';

    return (
      <div className="p-4 text-center text-muted-foreground">
        <div className="rounded-2xl border border-border/70 bg-black/20 px-4 py-6">
          <p className="text-sm">{emptyTitle}</p>
          {!hasForecastData && forecastNotice ? (
            <p className="mt-2 text-xs leading-relaxed text-muted-foreground/90">{forecastNotice}</p>
          ) : null}
          <p className="mt-2 text-[10px] uppercase tracking-[0.24em] text-muted-foreground/80">{emptyLabel}</p>
        </div>
      </div>
    );
  }

  const unavailable = isCellUnavailable(cell);
  const masked = isCellMasked(cell) && !unavailable;
  const maskLabel = getCellMaskLabel(cell);
  const maskSummary = getCellMaskSummary(cell);
  const maskReasonDescriptions = getCellMaskReasonDescriptions(cell);
  const { shapSource, drivers: shapData } = selectRiskDrivers(cell);

  const maxShap = Math.max(...shapData.map((d) => Math.abs(d.value)), 0.01);
  const coverageState = cell.coverageFlags?.sar_coverage_state;
  const limitingFactor = cell.limitingFactor ?? cell.shapContext?.limitingFactor;
  const fusionMethod = cell.fusionMethod ?? cell.shapContext?.fusionMethod;
  const hasResidualShadow = Boolean(cell.coverageFlags?.residual_shadow);
  const isCoverageGood = coverageState === 'good' || coverageState === 'full_coverage';
  const isCoverageLow = coverageState === 'low' || coverageState === 'low_coverage';
  const hasCoverageState = isCoverageGood || isCoverageLow || hasResidualShadow;

  if (unavailable) {
    return (
      <div className="space-y-3 p-4">
        <Card className="border border-border/70 bg-card/70 backdrop-blur-xl shadow-lg shadow-black/20">
          <CardHeader className="p-4 pb-2">
            <div className="flex items-center justify-between gap-3">
              <CardTitle className="text-xs text-muted-foreground uppercase tracking-[0.24em]">Grid State</CardTitle>
              <Badge className="rounded-full border-0 bg-slate-500/15 text-slate-300 text-xs">
                UNAVAILABLE TERRAIN
              </Badge>
            </div>
          </CardHeader>
          <CardContent className="p-4 pt-1 space-y-3">
            <div className="text-sm text-foreground">
              Terrain data is unavailable for grid [{cell.row},{cell.col}] within the strict DEM search radius. The cell is disabled and no forecast is synthesized.
            </div>
            <div className="grid grid-cols-1 gap-2 text-[11px] text-muted-foreground font-mono">
              <div>status: {cell.status ?? 'unavailable_terrain'}</div>
              <div>reason: {cell.availabilityReason ?? 'unavailable_terrain'}</div>
              <div>dynamic_model_version: {cell.dynamicModelVersion ?? 'n/a'}</div>
              <div>surrogate_model_version: {cell.surrogateModelVersion ?? 'n/a'}</div>
            </div>
          </CardContent>
        </Card>
      </div>
    );
  }

  if (masked) {
    return (
      <div className="space-y-3 p-4">
        <Card className="border border-border/70 bg-card/70 backdrop-blur-xl shadow-lg shadow-black/20">
          <CardHeader className="p-4 pb-2">
            <div className="flex items-center justify-between gap-3">
              <CardTitle className="text-xs text-muted-foreground uppercase tracking-[0.24em]">Grid State</CardTitle>
              <Tooltip>
                <TooltipTrigger asChild>
                  <Badge className="rounded-full border-0 bg-slate-500/15 text-slate-300 text-xs cursor-help">
                    {maskLabel}
                  </Badge>
                </TooltipTrigger>
                <TooltipContent side="bottom" className="text-xs max-w-[16rem]">
                  This grid cell is masked because it does not meet the Avalanche Path Terrain (APT) criteria (30–50° slope) or lacks snow support. The cell is disabled and no forecast is synthesized.
                </TooltipContent>
              </Tooltip>
            </div>
          </CardHeader>
          <CardContent className="p-4 pt-1 space-y-3">
            <div className="text-sm text-foreground">
              {maskSummary}
            </div>
            <div className="grid grid-cols-1 gap-2 text-[11px] text-muted-foreground font-mono">
              {cell.aptEligible === false && (
                <div>profile: {cell.aptProfile ?? 'apt_30_50_v1'}</div>
              )}
              {maskReasonDescriptions.map((reason) => (
                <div key={reason}>reason: {reason}</div>
              ))}
              <div>slope_angle_deg: {cell.terrainInputs?.slope_angle_deg?.toFixed(1) ?? 'n/a'}</div>
              <div>probability: {typeof cell.probability === 'number' ? (cell.probability * 100).toFixed(1) + '%' : 'n/a'}</div>
              <div>terrain_fused_risk_score: {cell.terrainFusedRiskScore ?? 'n/a'}</div>
            </div>
          </CardContent>
        </Card>
      </div>
    );
  }

  return (
    <div className="space-y-3 p-4">
      {/* Risk Score */}
      <Card className="border border-border/70 bg-card/70 backdrop-blur-xl shadow-lg shadow-black/20">
        <CardContent className="p-4">
          <div className="flex items-center justify-between mb-2">
            <span className="text-xs text-muted-foreground uppercase tracking-[0.24em]">Risk Level</span>
            <Badge
              className="text-xs font-mono rounded-full border-0"
              style={{ backgroundColor: getRiskColor(cell.riskScore), color: '#000' }}
            >
              {cell.riskScore} — {RISK_LABELS[cell.riskScore]}
            </Badge>
          </div>
          <div className="text-xs text-muted-foreground font-mono">
            Grid [{cell.row},{cell.col}] • {cell.problemType}
          </div>
          {limitingFactor && (
            <div className="mt-2 rounded-xl border border-sky-400/25 bg-sky-400/10 px-3 py-2">
              <Tooltip>
                <TooltipTrigger asChild>
                  <div className="text-[10px] uppercase tracking-[0.22em] text-sky-300 cursor-help">Limiting factor</div>
                </TooltipTrigger>
                <TooltipContent side="bottom" className="text-xs max-w-[18rem]">
                  IPA (Ideal Point Analysis) ranks cells by how close they are to the ideal risk profile. The limiting factor is the criterion that most constrains this cell's score. Chebyshev IPA uses the worst-case distance.
                </TooltipContent>
              </Tooltip>
              <div className="mt-1 text-xs font-mono text-foreground">
                {formatCriterionName(limitingFactor)}
                {typeof cell.chebyshevIpaScore === 'number' && Number.isFinite(cell.chebyshevIpaScore)
                  ? ` • IPA ${cell.chebyshevIpaScore.toFixed(2)}`
                  : ''}
              </div>
              {fusionMethod && (
                <div className="mt-1 text-[9px] font-mono text-muted-foreground">
                  fusion: {fusionMethod}
                </div>
              )}
            </div>
          )}
          {isCoverageGood && !hasResidualShadow && (
            <div className="mt-2 inline-flex items-center gap-1.5 rounded-full bg-emerald-500/15 border border-emerald-500/30 px-2 py-0.5">
              <span className="relative flex h-1.5 w-1.5">
                <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-emerald-400 opacity-75"></span>
                <span className="relative inline-flex rounded-full h-1.5 w-1.5 bg-emerald-500"></span>
              </span>
              <span className="text-[10px] font-mono text-emerald-300 uppercase tracking-wider">SAR COVERAGE: GOOD</span>
            </div>
          )}
          {isCoverageLow && !hasResidualShadow && (
            <div className="mt-2 inline-flex items-center gap-1.5 rounded-full bg-amber-500/15 border border-amber-500/30 px-2 py-0.5">
              <span className="relative flex h-1.5 w-1.5">
                <span className="relative inline-flex rounded-full h-1.5 w-1.5 bg-amber-500"></span>
              </span>
              <span className="text-[10px] font-mono text-amber-300 uppercase tracking-wider">SAR COVERAGE: LOW</span>
            </div>
          )}
          {hasResidualShadow && (
            <div className="mt-2 inline-flex items-center gap-1.5 rounded-full bg-red-500/15 border border-red-500/30 px-2 py-0.5">
              <span className="relative flex h-1.5 w-1.5">
                <span className="relative inline-flex rounded-full h-1.5 w-1.5 bg-red-500"></span>
              </span>
              <span className="text-[10px] font-mono text-red-300 uppercase tracking-wider">RESIDUAL SHADOW</span>
            </div>
          )}
          {!hasCoverageState && (
            <div className="mt-2 inline-flex items-center gap-1.5 rounded-full bg-slate-500/15 border border-slate-500/30 px-2 py-0.5">
              <span className="relative flex h-1.5 w-1.5">
                <span className="relative inline-flex rounded-full h-1.5 w-1.5 bg-slate-400"></span>
              </span>
              <span className="text-[10px] font-mono text-slate-300 uppercase tracking-wider">SAR COVERAGE: UNAVAILABLE</span>
            </div>
          )}
        </CardContent>
      </Card>

      {/* H/E/V Gauges */}
      <div className="grid grid-cols-3 gap-2">
        {[
          { label: 'Hazard', value: cell.hazard },
          { label: 'Exposure', value: cell.exposure },
          { label: 'Vulnerability', value: cell.vulnerability },
        ].map((g) => (
          <Card key={g.label} className="border border-border/70 bg-card/60 backdrop-blur-xl">
            <CardContent className="p-3 text-center">
              <div className="text-lg font-mono font-bold text-foreground">
                {(g.value * 100).toFixed(0)}%
              </div>
              <div className="text-[10px] text-muted-foreground uppercase tracking-[0.22em]">
                {g.label}
              </div>
            </CardContent>
          </Card>
        ))}
      </div>

      {/* Probability + uncertainty */}
      <Card className="border border-border/70 bg-card/60 backdrop-blur-xl">
        <CardContent className="p-4 space-y-2">
          <div className="flex items-center justify-between">
            <span className="text-xs text-muted-foreground uppercase tracking-[0.24em]">Calibrated Probability</span>
            <Badge className="rounded-full border-0 bg-emerald-500/15 text-emerald-400 text-xs">
              {(cell.probability ?? cell.riskScore / 5).toFixed(2)}
            </Badge>
          </div>
          <div className="text-[11px] text-muted-foreground flex items-center justify-between">
            <span>Confidence interval</span>
            <span className="font-mono text-foreground">
              {cell.confidenceLower !== undefined && cell.confidenceUpper !== undefined
                ? `${cell.confidenceLower.toFixed(2)} – ${cell.confidenceUpper.toFixed(2)}`
                : 'n/a'}
            </span>
          </div>
          <div className="text-[11px] text-muted-foreground flex items-center justify-between">
            <span>Uncertainty</span>
            <span className={cell.uncertaintyClass === 'high' ? 'text-gray-300 font-mono' : 'font-mono text-foreground'}>
              {cell.uncertaintyClass || 'unknown'}
            </span>
          </div>
        </CardContent>
      </Card>

      <Card className="border border-border/70 bg-card/60 backdrop-blur-xl">
        <CardContent className="p-4 space-y-2">
          <div className="flex items-center justify-between text-[11px]">
            <span className="text-muted-foreground uppercase tracking-[0.22em]">Dynamic Model</span>
            <span className="font-mono text-foreground">{cell.dynamicModelVersion ?? 'n/a'}</span>
          </div>
          <div className="flex items-center justify-between text-[11px]">
            <span className="text-muted-foreground uppercase tracking-[0.22em]">Surrogate Model</span>
            <span className="font-mono text-foreground">{cell.surrogateModelVersion ?? 'n/a'}</span>
          </div>
        </CardContent>
      </Card>

      {/* F13: Model Confidence Badge */}
      {cell.forecastConfidence && (
        <Card className="border border-border/70 bg-card/60 backdrop-blur-xl">
          <CardContent className="p-3 space-y-2">
            <div className="flex items-center justify-between">
              <span className="text-xs text-muted-foreground uppercase tracking-[0.24em]">Model Confidence</span>
              <Badge className={
                cell.forecastConfidence === 'high'
                  ? 'bg-emerald-500/15 text-emerald-400 border-0 text-[9px] px-2 py-0.5'
                  : cell.forecastConfidence === 'medium'
                    ? 'bg-amber-500/15 text-amber-300 border-0 text-[9px] px-2 py-0.5'
                    : cell.forecastConfidence === 'low'
                      ? 'bg-red-500/15 text-red-400 border-0 text-[9px] px-2 py-0.5'
                      : 'bg-slate-500/15 text-slate-300 border-0 text-[9px] px-2 py-0.5'
              }>
                {cell.forecastConfidence.toUpperCase()}
              </Badge>
            </div>
            {cell.brierScore != null && (
              <div className="text-[11px] text-muted-foreground flex items-center justify-between">
                <span>Brier score</span>
                <span className="font-mono text-foreground">{cell.brierScore.toFixed(4)}</span>
              </div>
            )}
            {cell.conformalLower != null && cell.conformalUpper != null && (
              <div className="text-[11px] text-muted-foreground flex items-center justify-between">
                <span>Conformal interval (90%)</span>
                <span className="font-mono text-foreground">
                  {cell.conformalLower.toFixed(2)} – {cell.conformalUpper.toFixed(2)}
                </span>
              </div>
            )}
          </CardContent>
        </Card>
      )}

      {/* Real Weather Values (Story #11 - Open-Meteo for all regions) */}
      {weatherSummary && (
        <Card className="border border-border/70 bg-card/60 backdrop-blur-xl">
          <CardHeader className="p-3 pb-1">
            <div className="flex items-center gap-2">
              <CardTitle className="text-xs text-emerald-400 uppercase tracking-[0.24em]">
                Weather Summary
              </CardTitle>
              <Badge className="bg-emerald-500/15 text-emerald-400 border-0 text-[8px] px-1.5 py-0 rounded-full">
                ● SUMMARY
              </Badge>
            </div>
          </CardHeader>
          <CardContent className="p-3 pt-1">
            <div className="grid grid-cols-2 gap-2 text-[10px]">
              <div className="flex justify-between">
                <span className="text-muted-foreground">Snowfall 24h</span>
                <span className="font-mono text-foreground">{formatWeatherValue(weatherSummary.snowfall_24h, 'cm')}</span>
              </div>
              <div className="flex justify-between">
                <span className="text-muted-foreground">Wind Speed</span>
                <span className="font-mono text-foreground">{formatWeatherValue(weatherSummary.wind_speed, 'km/h')}</span>
              </div>
              <div className="flex justify-between">
                <span className="text-muted-foreground">Temperature</span>
                <span className="font-mono text-foreground">{formatWeatherValue(weatherSummary.temperature, '°C')}</span>
              </div>
              <div className="flex justify-between">
                <span className="text-muted-foreground">Precipitation</span>
                <span className="font-mono text-foreground">{formatWeatherValue(weatherSummary.precipitation, 'mm')}</span>
              </div>
              <div className="flex justify-between">
                <span className="text-muted-foreground">Snow Depth</span>
                <span className="font-mono text-foreground">{formatWeatherValue(weatherSummary.snow_depth, 'cm')}</span>
              </div>
            </div>
          </CardContent>
        </Card>
      )}

      {/* Ensemble Probabilistic Weather (p10/p50/p90) */}
      {cell.ensembleAvailable && (
        <Card className="border border-border/70 bg-card/60 backdrop-blur-xl">
          <CardHeader className="p-3 pb-1">
            <div className="flex items-center gap-2">
              <CardTitle className="text-xs text-sky-400 uppercase tracking-[0.24em]">
                Ensemble Forecast
              </CardTitle>
              <Badge className="bg-sky-500/15 text-sky-400 border-0 text-[8px] px-1.5 py-0 rounded-full">
                ● PROBABILISTIC
              </Badge>
            </div>
          </CardHeader>
          <CardContent className="p-3 pt-1 space-y-2">
            <div className="text-[9px] text-muted-foreground font-mono">
              source: {cell.ensembleSource ?? 'open_meteo_ensemble_probabilistic_v1'}
            </div>
            <div className="grid grid-cols-3 gap-2 text-[10px]">
              <div className="text-center">
                <div className="text-muted-foreground uppercase tracking-wider mb-1">Temperature</div>
                <div className="font-mono text-foreground">
                  {cell.ensembleTempP10 != null ? `${cell.ensembleTempP10.toFixed(1)}°` : '—'}
                </div>
                <div className="font-mono text-sky-300">
                  {cell.ensembleTempP50 != null ? `${cell.ensembleTempP50.toFixed(1)}°` : '—'}
                </div>
                <div className="font-mono text-foreground">
                  {cell.ensembleTempP90 != null ? `${cell.ensembleTempP90.toFixed(1)}°` : '—'}
                </div>
                <div className="text-[8px] text-muted-foreground mt-0.5">p10 / p50 / p90</div>
              </div>
              <div className="text-center">
                <div className="text-muted-foreground uppercase tracking-wider mb-1">Snowfall</div>
                <div className="font-mono text-foreground">
                  {cell.ensembleSnowfallP10 != null ? `${cell.ensembleSnowfallP10.toFixed(1)}` : '—'}
                </div>
                <div className="font-mono text-sky-300">
                  {cell.ensembleSnowfallP50 != null ? `${cell.ensembleSnowfallP50.toFixed(1)}` : '—'}
                </div>
                <div className="font-mono text-foreground">
                  {cell.ensembleSnowfallP90 != null ? `${cell.ensembleSnowfallP90.toFixed(1)}` : '—'}
                </div>
                <div className="text-[8px] text-muted-foreground mt-0.5">p10 / p50 / p90 cm</div>
              </div>
              <div className="text-center">
                <div className="text-muted-foreground uppercase tracking-wider mb-1">Precip</div>
                <div className="font-mono text-foreground">
                  {cell.ensemblePrecipP10 != null ? `${cell.ensemblePrecipP10.toFixed(1)}` : '—'}
                </div>
                <div className="font-mono text-sky-300">
                  {cell.ensemblePrecipP50 != null ? `${cell.ensemblePrecipP50.toFixed(1)}` : '—'}
                </div>
                <div className="font-mono text-foreground">
                  {cell.ensemblePrecipP90 != null ? `${cell.ensemblePrecipP90.toFixed(1)}` : '—'}
                </div>
                <div className="text-[8px] text-muted-foreground mt-0.5">p10 / p50 / p90 mm</div>
              </div>
            </div>
          </CardContent>
        </Card>
      )}

      <Card className="border border-border/70 bg-card/60 backdrop-blur-xl">
        <CardHeader className="p-3 pb-1">
          <div className="flex items-center justify-between">
            <CardTitle className="text-xs text-muted-foreground uppercase tracking-[0.24em]">
              {shapSource === 'tree_shap' ? 'TreeSHAP Contributions' : 'Explainability Contributions'}
            </CardTitle>
            <Badge className={`text-[8px] rounded-full border-0 px-1.5 py-0 ${shapSource === 'tree_shap' ? 'bg-emerald-500/15 text-emerald-400' : 'bg-amber-500/15 text-amber-300'}`}>
              ● {shapSource === 'tree_shap' ? 'TREESHAP' : 'FALLBACK'}
            </Badge>
          </div>
        </CardHeader>
        <CardContent className="p-3 pt-1 space-y-1.5">
          {shapData.length === 0 ? (
            <div className="text-[11px] text-muted-foreground">
              {cell.explainabilityMode === 'heuristic_fallback'
                ? `TreeSHAP was unavailable for this batch${cell.explainabilityReason ? ` (${cell.explainabilityReason.replace(/_/g, ' ')})` : ''}, so the dashboard withholds a TreeSHAP claim for this cell.`
                : 'TreeSHAP contributions are missing from the batch artifact for this cell.'}
            </div>
          ) : (
            <>
              {shapData.map((d) => {
                const magnitude = Math.abs(d.value);
                const width = `${(magnitude / maxShap) * 100}%`;
                const positiveRisk = d.value >= 0;
                const barColor = positiveRisk ? 'hsl(8, 85%, 55%)' : 'hsl(156, 70%, 45%)';
                return (
                  <div key={d.feature} className="flex items-center gap-2">
                    <span className="text-[9px] text-secondary-foreground w-16 text-right truncate font-mono">
                      {d.label}
                    </span>
                    <div className="flex-1 h-4 bg-black/20 rounded-full overflow-hidden">
                      <div
                        className="h-full rounded-full transition-all duration-300"
                        style={{ width, backgroundColor: barColor }}
                      />
                    </div>
                    <span className="text-[9px] font-mono text-muted-foreground w-10 text-right">
                      {d.value >= 0 ? '+' : ''}{d.value.toFixed(3)}
                    </span>
                  </div>
                );
              })}
              <div className="pt-1 text-[9px] text-muted-foreground/70 font-mono">
                origin: {shapSource === 'tree_shap' ? 'batch TreeSHAP artifact' : 'heuristic fallback context'}
              </div>
            </>
          )}
        </CardContent>
      </Card>

      {/* F.1: Risk Explanation - Client-side natural language from SHAP values */}
      <Card className="border border-border/70 bg-card/60 backdrop-blur-xl">
        <CardHeader className="p-3 pb-1">
          <CardTitle className="text-xs text-muted-foreground uppercase tracking-[0.24em]">
            Risk Explanation
          </CardTitle>
        </CardHeader>
        <CardContent className="p-3 pt-1">
          <p className="text-sm leading-6 text-foreground/90">{buildRiskExplanation(cell)}</p>
        </CardContent>
      </Card>
    </div>
  );
}
