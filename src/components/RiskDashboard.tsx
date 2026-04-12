import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { RISK_LABELS } from '@/lib/constants';
import { getRiskColor, type GridCell } from '@/lib/gridUtils';

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
}

export default function RiskDashboard({ cell, weatherSummary }: Props) {
  if (!cell) {
    return (
      <div className="p-4 text-center text-muted-foreground">
        <p className="text-sm">Click a grid tile on the map to inspect risk details</p>
      </div>
    );
  }

  const shapData = Object.entries(cell.shapValues).map(([key, value]) => ({
    name: key.replace(/_/g, ' '),
    value: Number((value as number).toFixed(3)),
  })).sort((a, b) => b.value - a.value);

  const maxShap = Math.max(...shapData.map(d => d.value), 0.01);

  return (
    <div className="space-y-3 p-3">
      {/* Risk Score */}
      <Card className="border-0 bg-secondary/50">
        <CardContent className="p-4">
          <div className="flex items-center justify-between mb-2">
            <span className="text-xs text-muted-foreground uppercase tracking-wider">Risk Level</span>
            <Badge
              className="text-xs font-mono"
              style={{ backgroundColor: getRiskColor(cell.riskScore), color: '#000' }}
            >
              {cell.riskScore} — {RISK_LABELS[cell.riskScore]}
            </Badge>
          </div>
          <div className="text-xs text-muted-foreground font-mono">
            Grid [{cell.row},{cell.col}] • {cell.problemType}
          </div>
        </CardContent>
      </Card>

      {/* H/E/V Gauges */}
      <div className="grid grid-cols-3 gap-2">
        {[
          { label: 'Hazard', value: cell.hazard },
          { label: 'Exposure', value: cell.exposure },
          { label: 'Vulnerability', value: cell.vulnerability },
        ].map((g) => (
          <Card key={g.label} className="border-0 bg-secondary/50">
            <CardContent className="p-3 text-center">
              <div className="text-lg font-mono font-bold text-foreground">
                {(g.value * 100).toFixed(0)}%
              </div>
              <div className="text-[10px] text-muted-foreground uppercase tracking-wider">
                {g.label}
              </div>
            </CardContent>
          </Card>
        ))}
      </div>

      {/* Real Weather Values (Story #11 - Open-Meteo for all regions) */}
      {weatherSummary && (
        <Card className="border-0 bg-secondary/50">
          <CardHeader className="p-3 pb-1">
            <div className="flex items-center gap-2">
              <CardTitle className="text-xs text-green-400 uppercase tracking-wider">
                Live Weather (Open-Meteo)
              </CardTitle>
              <Badge className="bg-green-500/20 text-green-400 border-0 text-[8px] px-1.5 py-0">
                ● LIVE
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
                <span className="font-mono text-foreground">{weatherSummary.snow_depth === '0.0' ? 'N/A' : `${weatherSummary.snow_depth} cm`}</span>
              </div>
            </div>
          </CardContent>
        </Card>
      )}

      {/* SHAP Values - CSS bar chart instead of recharts */}
      <Card className="border-0 bg-secondary/50">
        <CardHeader className="p-3 pb-1">
          <CardTitle className="text-xs text-muted-foreground uppercase tracking-wider">
            SHAP Feature Importance
          </CardTitle>
        </CardHeader>
        <CardContent className="p-3 pt-1 space-y-1.5">
          {shapData.map((d, i) => (
            <div key={d.name} className="flex items-center gap-2">
              <span className="text-[9px] text-secondary-foreground w-16 text-right truncate font-mono">
                {d.name}
              </span>
              <div className="flex-1 h-4 bg-muted rounded overflow-hidden">
                <div
                  className="h-full rounded transition-all duration-300"
                  style={{
                    width: `${(d.value / maxShap) * 100}%`,
                    backgroundColor: `hsl(199, ${70 + i * 4}%, ${55 - i * 5}%)`,
                  }}
                />
              </div>
              <span className="text-[9px] font-mono text-muted-foreground w-10 text-right">
                {d.value.toFixed(3)}
              </span>
            </div>
          ))}
        </CardContent>
      </Card>
    </div>
  );
}
