import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { RISK_LABELS } from '@/lib/constants';
import { getRiskColor, type GridCell } from '@/lib/gridUtils';
import type { ShapResult } from '@/lib/shapLoader';

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
  shapResult?: ShapResult | null;
}

// F.1: Generate natural language explanation from SHAP values
function generateRiskExplanation(cell: GridCell): string {
  const shapEntries = Object.entries(cell.shapValues)
    .map(([key, value]) => ({ name: key.replace(/_/g, ' '), value: Number(value) }))
    .sort((a, b) => Math.abs(b.value) - Math.abs(a.value));

  const topPositive = shapEntries.find(e => e.value > 0);
  const topNegative = shapEntries.find(e => e.value < 0);
  const riskLevel = RISK_LABELS[cell.riskScore];

  // Generate contextual explanation based on risk level
  if (cell.riskScore <= 2) {
    const reason = topNegative
      ? `${topNegative.name} (${topNegative.value.toFixed(3)}) stabilizes conditions`
      : 'favorable terrain and weather patterns';
    const caution = topPositive
      ? `Watch for ${topPositive.name} (+${topPositive.value.toFixed(3)}) as a minor risk factor`
      : 'Overall conditions are stable';
    return `Low risk (${riskLevel}) due to ${reason}. ${caution}.`;
  } else if (cell.riskScore >= 4) {
    const driver = topPositive
      ? `${topPositive.name} (+${topPositive.value.toFixed(3)}) significantly increases risk`
      : 'multiple adverse conditions';
    const mitigation = topNegative
      ? `Partially offset by ${topNegative.name} (${topNegative.value.toFixed(3)})`
      : 'No significant stabilizing factors present';
    return `High risk (${riskLevel}) driven by ${driver}. ${mitigation}.`;
  } else {
    const driver = topPositive
      ? `${topPositive.name} (+${topPositive.value.toFixed(3)}) drives moderate risk`
      : 'uncertain conditions';
    const offset = topNegative
      ? `tempered by ${topNegative.name} (${topNegative.value.toFixed(3)})`
      : '';
    return `Moderate risk (${riskLevel}). ${driver} ${offset}.`.trim();
  }
}

export default function RiskDashboard({ cell, weatherSummary, shapResult }: Props) {
  if (!cell) {
    return (
      <div className="p-4 text-center text-muted-foreground">
        <div className="rounded-2xl border border-border/70 bg-black/20 px-4 py-6">
          <p className="text-sm">Click a grid tile on the map to inspect risk details</p>
          <p className="mt-2 text-[10px] uppercase tracking-[0.24em] text-muted-foreground/80">Telemetry standby</p>
        </div>
      </div>
    );
  }

  // P1.2: Prefer real TreeSHAP from forecast_shap_cache when loaded; fall
  // back to the inline heuristic from cell.shapValues and clearly label the
  // origin so users never see heuristic values framed as TreeSHAP.
  const realShap = shapResult?.origin === 'forecast_shap_cache' ? shapResult.topFeatures : null;
  const shapSource: 'treeshap' | 'heuristic' = realShap && realShap.length > 0 ? 'treeshap' : 'heuristic';
  const shapData = realShap && realShap.length > 0
    ? realShap.slice(0, 5).map((item) => ({
        name: item.feature.replace(/_/g, ' '),
        value: Number(item.shap_value.toFixed(3)),
        featureValue: Number(item.feature_value.toFixed(3)),
      }))
    : Object.entries(cell.shapValues)
        .map(([key, value]) => ({
          name: key.replace(/_/g, ' '),
          value: Number((value as number).toFixed(3)),
          featureValue: undefined as number | undefined,
        }))
        .sort((a, b) => Math.abs(b.value) - Math.abs(a.value))
        .slice(0, 5);

  const maxShap = Math.max(...shapData.map((d) => Math.abs(d.value)), 0.01);
  const coverageState = cell.coverageFlags?.sar_coverage_state;
  const hasResidualShadow = Boolean(cell.coverageFlags?.residual_shadow);
  const isCoverageGood = coverageState === 'good' || coverageState === 'full_coverage';
  const isCoverageLow = coverageState === 'low' || coverageState === 'low_coverage';

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
                <span className="font-mono text-foreground">{weatherSummary.snowfall_24h} cm</span>
              </div>
              <div className="flex justify-between">
                <span className="text-muted-foreground">Wind Speed</span>
                <span className="font-mono text-foreground">{weatherSummary.wind_speed} km/h</span>
              </div>
              <div className="flex justify-between">
                <span className="text-muted-foreground">Temperature</span>
                <span className="font-mono text-foreground">{weatherSummary.temperature}°C</span>
              </div>
              <div className="flex justify-between">
                <span className="text-muted-foreground">Precipitation</span>
                <span className="font-mono text-foreground">{weatherSummary.precipitation} mm</span>
              </div>
              <div className="flex justify-between">
                <span className="text-muted-foreground">Snow Depth</span>
                <span className="font-mono text-foreground">{weatherSummary.snow_depth && weatherSummary.snow_depth !== 'N/A' ? `${weatherSummary.snow_depth} cm` : '0 cm'}</span>
              </div>
            </div>
          </CardContent>
        </Card>
      )}

      {/* P1.2: SHAP bars w/ honest origin label. Real TreeSHAP uses a
          diverging scale (red = risk-increasing, green = risk-decreasing);
          heuristic fallback uses the original green monochrome palette. */}
      <Card className="border border-border/70 bg-card/60 backdrop-blur-xl">
        <CardHeader className="p-3 pb-1">
          <div className="flex items-center justify-between">
            <CardTitle className="text-xs text-muted-foreground uppercase tracking-[0.24em]">
              {shapSource === 'treeshap' ? 'TreeSHAP Contributions' : 'Feature Contributions'}
            </CardTitle>
            <Badge
              className={`text-[8px] rounded-full border-0 px-1.5 py-0 ${
                shapSource === 'treeshap'
                  ? 'bg-emerald-500/15 text-emerald-400'
                  : 'bg-amber-500/15 text-amber-400'
              }`}
            >
              {shapSource === 'treeshap' ? '● TREESHAP' : '● HEURISTIC'}
            </Badge>
          </div>
        </CardHeader>
        <CardContent className="p-3 pt-1 space-y-1.5">
          {shapData.map((d) => {
            const magnitude = Math.abs(d.value);
            const width = `${(magnitude / maxShap) * 100}%`;
            const positiveRisk = d.value >= 0;
            const barColor = shapSource === 'treeshap'
              ? (positiveRisk ? 'hsl(8, 85%, 55%)' : 'hsl(156, 70%, 45%)')
              : 'hsl(156, 72%, 50%)';
            return (
              <div key={d.name} className="flex items-center gap-2">
                <span className="text-[9px] text-secondary-foreground w-16 text-right truncate font-mono">
                  {d.name}
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
            {shapSource === 'treeshap'
              ? `origin: forecast_shap_cache${shapResult?.modelVersion ? ` · ${shapResult.modelVersion.slice(0, 10)}` : ''}`
              : 'origin: inline_cell_context (heuristic weighted features)'}
          </div>
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
          <p className="text-sm leading-6 text-foreground/90">{generateRiskExplanation(cell)}</p>
        </CardContent>
      </Card>
    </div>
  );
}
