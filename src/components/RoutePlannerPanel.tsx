import { useMemo, useState } from 'react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { Label } from '@/components/ui/label';
import { AlertTriangle, Route, Shield, ShieldAlert } from 'lucide-react';

export interface RouteCell {
  row: number;
  col: number;
  lat: number;
  lng: number;
  risk_score: number;
  risk_level: number;
}

export interface RouteStepData {
  step_index: number;
  row: number;
  col: number;
  lat: number;
  lng: number;
  risk_score: number;
  risk_level: number;
  cumulative_cost: number;
}

export interface SafeRouteData {
  status: string;
  start_cell: string;
  end_cell: string;
  grid_size: number;
  algorithm: string;
  step_count: number;
  total_cost: number;
  max_risk: number;
  avg_risk: number;
  blocked_cells: string[];
  steps: RouteStepData[];
}

interface RoutePlannerPanelProps {
  cells: RouteCell[];
  gridSize: number;
  onRouteComputed?: (route: SafeRouteData) => void;
}

const RISK_THRESHOLD = 3.5;

function riskColor(score: number): string {
  if (score >= 4) return 'bg-red-600';
  if (score >= 3) return 'bg-orange-500';
  if (score >= 2) return 'bg-yellow-500';
  if (score >= 1) return 'bg-green-500';
  return 'bg-slate-300';
}

function riskLabel(score: number): string {
  if (score >= 4.5) return 'Extreme';
  if (score >= 3.5) return 'High';
  if (score >= 2.5) return 'Moderate';
  if (score >= 1.5) return 'Low';
  if (score > 0) return 'Very Low';
  return 'No Risk';
}

export function RoutePlannerPanel({ cells, gridSize, onRouteComputed }: RoutePlannerPanelProps) {
  const [startRow, setStartRow] = useState(0);
  const [startCol, setStartCol] = useState(0);
  const [endRow, setEndRow] = useState(gridSize - 1);
  const [endCol, setEndCol] = useState(gridSize - 1);
  const [route, setRoute] = useState<SafeRouteData | null>(null);
  const [computing, setComputing] = useState(false);

  const blockedCells = useMemo(
    () => cells.filter((c) => c.risk_score >= RISK_THRESHOLD),
    [cells],
  );

  const routeCellsSet = useMemo(() => {
    if (!route) return new Set<string>();
    return new Set(route.steps.map((s) => `r${s.row}c${s.col}`));
  }, [route]);

  const computeRoute = () => {
    setComputing(true);
    const grid: number[][] = Array.from({ length: gridSize }, () =>
      Array.from({ length: gridSize }, () => 0),
    );
    for (const cell of cells) {
      if (cell.row < gridSize && cell.col < gridSize) {
        grid[cell.row][cell.col] = cell.risk_score;
      }
    }

    const result = computeSafeRouteLocal(
      grid,
      gridSize,
      [startRow, startCol],
      [endRow, endCol],
      RISK_THRESHOLD,
    );
    setRoute(result);
    onRouteComputed?.(result);
    setComputing(false);
  };

  const isSafe = route?.status === 'ok' && route.max_risk < RISK_THRESHOLD;

  return (
    <Card className="w-full">
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <Route className="h-5 w-5" />
          Safe-Route Planner (F10)
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-4">
        {blockedCells.length > 0 && (
          <div className="flex items-center gap-2 text-sm text-orange-600">
            <ShieldAlert className="h-4 w-4" />
            {blockedCells.length} blocked cell{blockedCells.length > 1 ? 's' : ''} (risk ≥ {RISK_THRESHOLD})
          </div>
        )}

        <div className="grid grid-cols-2 gap-4">
          <div className="space-y-2">
            <Label>Start (Row, Col)</Label>
            <div className="flex gap-2">
              <Select value={String(startRow)} onValueChange={(v) => setStartRow(Number(v))}>
                <SelectTrigger className="w-20"><SelectValue /></SelectTrigger>
                <SelectContent>
                  {Array.from({ length: gridSize }, (_, i) => (
                    <SelectItem key={i} value={String(i)}>{i}</SelectItem>
                  ))}
                </SelectContent>
              </Select>
              <Select value={String(startCol)} onValueChange={(v) => setStartCol(Number(v))}>
                <SelectTrigger className="w-20"><SelectValue /></SelectTrigger>
                <SelectContent>
                  {Array.from({ length: gridSize }, (_, i) => (
                    <SelectItem key={i} value={String(i)}>{i}</SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
          </div>
          <div className="space-y-2">
            <Label>End (Row, Col)</Label>
            <div className="flex gap-2">
              <Select value={String(endRow)} onValueChange={(v) => setEndRow(Number(v))}>
                <SelectTrigger className="w-20"><SelectValue /></SelectTrigger>
                <SelectContent>
                  {Array.from({ length: gridSize }, (_, i) => (
                    <SelectItem key={i} value={String(i)}>{i}</SelectItem>
                  ))}
                </SelectContent>
              </Select>
              <Select value={String(endCol)} onValueChange={(v) => setEndCol(Number(v))}>
                <SelectTrigger className="w-20"><SelectValue /></SelectTrigger>
                <SelectContent>
                  {Array.from({ length: gridSize }, (_, i) => (
                    <SelectItem key={i} value={String(i)}>{i}</SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
          </div>
        </div>

        <Button onClick={computeRoute} disabled={computing} className="w-full">
          {computing ? 'Computing...' : 'Compute Safe Route'}
        </Button>

        {route && (
          <div className="space-y-3">
            <div className="flex items-center gap-2">
              {route.status === 'ok' ? (
                <Badge variant={isSafe ? 'default' : 'destructive'} className="gap-1">
                  <Shield className="h-3 w-3" />
                  {isSafe ? 'Safe Route Found' : 'Route Passes High-Risk Cells'}
                </Badge>
              ) : (
                <Badge variant="destructive" className="gap-1">
                  <AlertTriangle className="h-3 w-3" />
                  {route.status === 'blocked' ? 'Start/End Blocked' : 'No Path Available'}
                </Badge>
              )}
            </div>

            {route.status === 'ok' && (
              <div className="grid grid-cols-3 gap-2 text-sm">
                <div className="rounded-md bg-slate-100 p-2">
                  <div className="text-xs text-slate-500">Steps</div>
                  <div className="font-semibold">{route.step_count}</div>
                </div>
                <div className="rounded-md bg-slate-100 p-2">
                  <div className="text-xs text-slate-500">Max Risk</div>
                  <div className="font-semibold">{route.max_risk.toFixed(2)}</div>
                </div>
                <div className="rounded-md bg-slate-100 p-2">
                  <div className="text-xs text-slate-500">Avg Risk</div>
                  <div className="font-semibold">{route.avg_risk.toFixed(2)}</div>
                </div>
              </div>
            )}

            {gridSize <= 20 && (
              <div className="overflow-x-auto">
                <div
                  className="grid gap-px"
                  style={{ gridTemplateColumns: `repeat(${gridSize}, minmax(0, 1fr))` }}
                >
                  {Array.from({ length: gridSize * gridSize }, (_, idx) => {
                    const row = Math.floor(idx / gridSize);
                    const col = idx % gridSize;
                    const cell = cells.find((c) => c.row === row && c.col === col);
                    const score = cell?.risk_score ?? 0;
                    const cellId = `r${row}c${col}`;
                    const isRoute = routeCellsSet.has(cellId);
                    const isStart = row === startRow && col === startCol;
                    const isEnd = row === endRow && col === endCol;
                    const isBlocked = score >= RISK_THRESHOLD;
                    return (
                      <div
                        key={idx}
                        className={`h-5 w-5 rounded-sm ${riskColor(score)} ${
                          isRoute ? 'ring-2 ring-blue-600 ring-offset-1' : ''
                        } ${isBlocked ? 'opacity-60' : ''} ${
                          isStart ? 'ring-2 ring-green-700' : ''
                        } ${isEnd ? 'ring-2 ring-purple-700' : ''
                        }`}
                        title={`r${row}c${col} — ${riskLabel(score)} (${score.toFixed(1)})`}
                      />
                    );
                  })}
                </div>
              </div>
            )}
          </div>
        )}
      </CardContent>
    </Card>
  );
}

// ---------------------------------------------------------------------------
// Local Dijkstra implementation (mirrors backend/common/route_planner.py)
// ---------------------------------------------------------------------------

function computeSafeRouteLocal(
  grid: number[][],
  gridSize: number,
  start: [number, number],
  end: [number, number],
  threshold: number,
): SafeRouteData {
  const startId = `r${start[0]}c${start[1]}`;
  const endId = `r${end[0]}c${end[1]}`;
  const blocked: string[] = [];

  for (let r = 0; r < gridSize; r++) {
    for (let c = 0; c < gridSize; c++) {
      if (grid[r][c] >= threshold) blocked.push(`r${r}c${c}`);
    }
  }

  if (grid[start[0]][start[1]] >= threshold || grid[end[0]][end[1]] >= threshold) {
    return {
      status: 'blocked',
      start_cell: startId,
      end_cell: endId,
      grid_size: gridSize,
      algorithm: 'dijkstra',
      step_count: 0,
      total_cost: 0,
      max_risk: 0,
      avg_risk: 0,
      blocked_cells: blocked,
      steps: [],
    };
  }

  const blockedSet = new Set(blocked);
  const directions = [
    [-1, 0], [1, 0], [0, -1], [0, 1],
    [-1, -1], [-1, 1], [1, -1], [1, 1],
  ];

  const dist: Record<string, number> = { [startId]: 0 };
  const prev: Record<string, string | null> = { [startId]: null };
  const pq: [number, string][] = [[0, startId]];

  while (pq.length > 0) {
    pq.sort((a, b) => a[0] - b[0]);
    const [curDist, curId] = pq.shift()!;
    if (curId === endId) break;
    if (curDist > (dist[curId] ?? Infinity)) continue;

    const [r, c] = curId.slice(1).split('c').map(Number);
    for (const [dr, dc] of directions) {
      const nr = r + dr;
      const nc = c + dc;
      if (nr < 0 || nr >= gridSize || nc < 0 || nc >= gridSize) continue;
      const nid = `r${nr}c${nc}`;
      if (blockedSet.has(nid)) continue;
      const distance = Math.sqrt(dr * dr + dc * dc);
      const weight = distance * (1 + grid[nr][nc]);
      const newDist = curDist + weight;
      if (newDist < (dist[nid] ?? Infinity)) {
        dist[nid] = newDist;
        prev[nid] = curId;
        pq.push([newDist, nid]);
      }
    }
  }

  if (!(endId in dist)) {
    return {
      status: 'no_path',
      start_cell: startId,
      end_cell: endId,
      grid_size: gridSize,
      algorithm: 'dijkstra',
      step_count: 0,
      total_cost: 0,
      max_risk: 0,
      avg_risk: 0,
      blocked_cells: blocked,
      steps: [],
    };
  }

  const path: string[] = [];
  let cur: string | null = endId;
  while (cur !== null) {
    path.unshift(cur);
    cur = prev[cur] ?? null;
  }

  const steps: RouteStepData[] = path.map((cid, idx) => {
    const [r, c] = cid.slice(1).split('c').map(Number);
    return {
      step_index: idx,
      row: r,
      col: c,
      lat: 0,
      lng: 0,
      risk_score: grid[r][c],
      risk_level: Math.floor(grid[r][c]),
      cumulative_cost: dist[cid],
    };
  });

  const maxRisk = Math.max(...steps.map((s) => s.risk_score));
  const avgRisk = steps.reduce((sum, s) => sum + s.risk_score, 0) / steps.length;

  return {
    status: 'ok',
    start_cell: startId,
    end_cell: endId,
    grid_size: gridSize,
    algorithm: 'dijkstra',
    step_count: steps.length,
    total_cost: Math.round(dist[endId] * 10000) / 10000,
    max_risk: Math.round(maxRisk * 1000) / 1000,
    avg_risk: Math.round(avgRisk * 1000) / 1000,
    blocked_cells: blocked,
    steps,
  };
}
