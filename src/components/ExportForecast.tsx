import { useState } from 'react';
import { Button } from '@/components/ui/button';
import { Check, FileSpreadsheet, FileJson, FileSpreadsheet as CsvIcon } from 'lucide-react';
import { toast } from 'sonner';
import type { GridCell } from '@/lib/gridUtils';
import type { AvalancheEvent } from '@/components/HistoricalEventsToggle';

interface Props {
  grid?: { cells: GridCell[]; timestamp: string; bbox: [number, number, number, number] } | null;
  events?: AvalancheEvent[];
  regionName?: string;
  hour?: number;
  canExport?: boolean;
}

export default function ExportForecast({ grid, events = [], regionName = 'Unknown', hour = 0, canExport = false }: Props) {
  const [copied, setCopied] = useState<'csv' | 'json' | null>(null);

  const downloadCSV = () => {
    if (!canExport || !grid || grid.cells.length === 0) {
      toast.info('Run a forecast first to export data');
      return;
    }

    // CSV Header — guard against cells with missing shapValues (e.g. simulated grid)
    const firstShapKeys = Object.keys(grid.cells[0]?.shapValues ?? {});
    const headers = ['row', 'col', 'lat', 'lng', 'riskScore', 'probability', 'confidenceLower', 'confidenceUpper', 'uncertaintySpan', 'uncertaintyClass', 'hazard', 'exposure', 'vulnerability', 'problemType', ...firstShapKeys];
    
    // CSV Rows
    const rows = grid.cells.map(cell => [
      cell.row,
      cell.col,
      cell.lat.toFixed(6),
      cell.lng.toFixed(6),
      cell.riskScore,
      (cell.probability ?? cell.riskScore / 5).toFixed(3),
      (cell.confidenceLower ?? 0).toFixed(3),
      (cell.confidenceUpper ?? 0).toFixed(3),
      (cell.uncertaintySpan ?? 0).toFixed(3),
      cell.uncertaintyClass ?? 'unknown',
      cell.hazard.toFixed(3),
      cell.exposure.toFixed(3),
      cell.vulnerability.toFixed(3),
      cell.problemType,
      ...firstShapKeys.map(k => (cell.shapValues?.[k] ?? 0).toFixed(3))
    ]);

    const csv = [headers.join(','), ...rows.map(r => r.join(','))].join('\n');
    const blob = new Blob([csv], { type: 'text/csv' });
    const url = URL.createObjectURL(blob);
    
    const a = document.createElement('a');
    a.href = url;
    a.download = `avalanche-forecast-${regionName.replace(/\s+/g, '-').toLowerCase()}-h${hour}.csv`;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);

    toast.success(`Exported ${grid.cells.length} grid cells to CSV`);
  };

  const downloadJSON = () => {
    if (!canExport || !grid || grid.cells.length === 0) {
      toast.info('Run a forecast first to export data');
      return;
    }

    const data = {
      metadata: {
        region: regionName,
        hour: hour,
        timestamp: grid.timestamp,
        bbox: grid.bbox,
        totalCells: grid.cells.length,
        exportedAt: new Date().toISOString()
      },
      grid: grid.cells.map((cell) => ({
        ...cell,
        probability: cell.probability ?? cell.riskScore / 5,
        confidenceLower: cell.confidenceLower ?? null,
        confidenceUpper: cell.confidenceUpper ?? null,
        uncertaintySpan: cell.uncertaintySpan ?? null,
        uncertaintyClass: cell.uncertaintyClass ?? null,
        runoutSeed: cell.runoutSeed ?? false,
        inferenceBackend: cell.inferenceBackend ?? 'client_simulation',
        modelVersion: cell.modelVersion ?? null,
        calibrationProfile: cell.calibrationProfile ?? null,
      })),
      events: events.map(e => ({
        id: e.id,
        lat: e.lat,
        lng: e.lng,
        severity: e.severity,
        confidence: e.confidence,
        description: e.description,
        source: e.source,
        event_type: e.event_type,
        timestamp: e.timestamp
      }))
    };

    const blob = new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' });
    const url = URL.createObjectURL(blob);
    
    const a = document.createElement('a');
    a.href = url;
    a.download = `avalanche-forecast-${regionName.replace(/\s+/g, '-').toLowerCase()}-h${hour}.json`;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);

    toast.success(`Exported forecast + ${events.length} events to JSON`);
  };

  const handleExport = () => {
    downloadCSV();
    setCopied('csv');
    setTimeout(() => setCopied(null), 2000);
  };

  return (
    <div className="flex items-center gap-2">
      <Button
        variant="outline"
        className="h-9 text-xs font-semibold gap-2 glass-panel border-0"
        disabled={!canExport}
        onClick={handleExport}
      >
        {copied === 'csv' ? <Check className="h-4 w-4 text-green-400" /> : <CsvIcon className="h-4 w-4" />}
        CSV
      </Button>
      <Button
        variant="outline"
        className="h-9 text-xs font-semibold gap-2 glass-panel border-0"
        disabled={!canExport}
        onClick={() => {
          downloadJSON();
          setCopied('json');
          setTimeout(() => setCopied(null), 2000);
        }}
      >
        {copied === 'json' ? <Check className="h-4 w-4 text-green-400" /> : <FileJson className="h-4 w-4" />}
        JSON
      </Button>
    </div>
  );
}
