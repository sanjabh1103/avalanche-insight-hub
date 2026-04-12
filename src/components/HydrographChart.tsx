import { useMemo } from 'react';
import { LineChart, Line, XAxis, YAxis, Tooltip, ResponsiveContainer, CartesianGrid, Legend } from 'recharts';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import type { GridCell } from '@/lib/gridUtils';

interface Props {
  hourlyGrids: GridCell[][] | null;
  selectedCell: GridCell | null;
}

export default function HydrographChart({ hourlyGrids, selectedCell }: Props) {
  const data = useMemo(() => {
    if (!hourlyGrids || !selectedCell) return [];
    return hourlyGrids.map((grid, hour) => {
      const cell = grid.find(c => c.row === selectedCell.row && c.col === selectedCell.col);
      if (!cell) return null;
      return {
        hour: `+${hour}h`,
        risk: cell.riskScore,
        hazard: +(cell.hazard * 100).toFixed(0),
        exposure: +(cell.exposure * 100).toFixed(0),
        snowfall: +(cell.shapValues?.snowfall_24h ?? 0).toFixed(3),
      };
    }).filter(Boolean);
  }, [hourlyGrids, selectedCell]);

  if (!data.length) {
    return (
      <Card className="border-0 bg-secondary/50">
        <CardContent className="p-4 text-center text-muted-foreground text-xs">
          Run a forecast and select a cell to see the hydrograph
        </CardContent>
      </Card>
    );
  }

  return (
    <Card className="border-0 bg-secondary/50">
      <CardHeader className="p-3 pb-1">
        <CardTitle className="text-xs text-muted-foreground uppercase tracking-wider">
          Risk Evolution — Cell [{selectedCell!.row},{selectedCell!.col}]
        </CardTitle>
      </CardHeader>
      <CardContent className="p-3 pt-1">
        <ResponsiveContainer width="100%" height={180}>
          <LineChart data={data} margin={{ top: 5, right: 5, bottom: 5, left: -20 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="hsl(220 14% 20%)" />
            <XAxis dataKey="hour" tick={{ fontSize: 9, fill: 'hsl(215 14% 55%)' }} interval={Math.floor(data.length / 8)} />
            <YAxis tick={{ fontSize: 9, fill: 'hsl(215 14% 55%)' }} domain={[0, 5]} />
            <Tooltip
              contentStyle={{ background: 'hsl(220 18% 10%)', border: '1px solid hsl(220 14% 18%)', fontSize: 11 }}
              labelStyle={{ color: 'hsl(210 20% 92%)' }}
            />
            <Legend wrapperStyle={{ fontSize: 10 }} />
            <Line type="monotone" dataKey="risk" stroke="hsl(0 72% 51%)" strokeWidth={2} dot={false} name="Danger" />
            <Line type="monotone" dataKey="hazard" stroke="hsl(199 89% 48%)" strokeWidth={1.5} dot={false} name="Hazard %" />
            <Line type="monotone" dataKey="exposure" stroke="hsl(45 93% 47%)" strokeWidth={1} dot={false} name="Exposure %" />
          </LineChart>
        </ResponsiveContainer>
      </CardContent>
    </Card>
  );
}
