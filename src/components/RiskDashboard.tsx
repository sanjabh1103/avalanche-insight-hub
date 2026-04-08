import { BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, Cell } from 'recharts';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { RISK_LABELS } from '@/lib/constants';
import { getRiskColor, type GridCell } from '@/lib/gridUtils';

interface Props {
  cell: GridCell | null;
}

export default function RiskDashboard({ cell }: Props) {
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

      {/* SHAP Values */}
      <Card className="border-0 bg-secondary/50">
        <CardHeader className="p-3 pb-1">
          <CardTitle className="text-xs text-muted-foreground uppercase tracking-wider">
            SHAP Feature Importance
          </CardTitle>
        </CardHeader>
        <CardContent className="p-3 pt-0">
          <div className="h-40">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={shapData} layout="vertical" margin={{ left: 70, right: 8, top: 4, bottom: 4 }}>
                <XAxis type="number" tick={{ fontSize: 10, fill: 'hsl(215 14% 55%)' }} />
                <YAxis
                  type="category"
                  dataKey="name"
                  tick={{ fontSize: 9, fill: 'hsl(210 20% 82%)' }}
                  width={65}
                />
                <Tooltip
                  contentStyle={{
                    background: 'hsl(220 18% 10%)',
                    border: '1px solid hsl(220 14% 18%)',
                    borderRadius: '8px',
                    fontSize: 11,
                    color: 'hsl(210 20% 92%)',
                  }}
                />
                <Bar dataKey="value" radius={[0, 4, 4, 0]}>
                  {shapData.map((_, i) => (
                    <Cell key={i} fill={`hsl(199, ${70 + i * 4}%, ${55 - i * 5}%)`} />
                  ))}
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          </div>
        </CardContent>
      </Card>
    </div>
  );
}
