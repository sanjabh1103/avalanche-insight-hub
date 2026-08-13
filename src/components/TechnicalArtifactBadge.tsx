import { Badge } from '@/components/ui/badge';
import { AlertTriangle, FileCheck2, FileX2 } from 'lucide-react';
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from '@/components/ui/tooltip';

interface TechnicalArtifactBadgeProps {
  artifactMode?: string;
  artifactPath?: string;
  artifactError?: string;
  technicalArtifactEnabled?: boolean;
  artifactId?: string;
  artifactSha256?: string;
  runId?: string;
  calibrationState?: string;
  shadowLabel?: boolean;
}

export function TechnicalArtifactBadge({
  artifactMode,
  artifactPath,
  artifactError,
  technicalArtifactEnabled = false,
  artifactId,
  artifactSha256,
  runId,
  calibrationState,
  shadowLabel = false,
}: TechnicalArtifactBadgeProps) {
  if (!technicalArtifactEnabled) {
    return null;
  }

  if (artifactError || !artifactPath) {
    return (
      <Badge variant="destructive" className="gap-1.5">
        <FileX2 className="h-3.5 w-3.5" />
        <span>Artifact Missing</span>
      </Badge>
    );
  }

  if (artifactMode === 'technical_artifact') {
    const shaShort = artifactSha256 ? artifactSha256.slice(0, 12) : 'unavailable';
    const tooltipRows: { label: string; value: string }[] = [];
    if (runId) tooltipRows.push({ label: 'Run ID', value: runId });
    if (artifactId) tooltipRows.push({ label: 'Artifact ID', value: artifactId });
    tooltipRows.push({ label: 'SHA-256', value: shaShort });
    if (calibrationState) tooltipRows.push({ label: 'Calibration', value: calibrationState });
    tooltipRows.push({ label: 'Release Mode', value: 'technical_artifact' });
    if (shadowLabel) tooltipRows.push({ label: 'Shadow', value: 'Research shadow output — not an official warning' });

    return (
      <TooltipProvider delayDuration={200}>
        <Tooltip>
          <TooltipTrigger asChild>
            <Badge variant="default" className="gap-1.5 bg-blue-600 hover:bg-blue-700 cursor-help">
              <FileCheck2 className="h-3.5 w-3.5" />
              <span>Technical Artifact</span>
            </Badge>
          </TooltipTrigger>
          <TooltipContent side="bottom" className="max-w-xs">
            <div className="flex flex-col gap-1 text-xs">
              {tooltipRows.map((row) => (
                <div key={row.label} className="flex gap-2">
                  <span className="font-semibold text-muted-foreground">{row.label}:</span>
                  <span className="font-mono break-all">{row.value}</span>
                </div>
              ))}
            </div>
          </TooltipContent>
        </Tooltip>
        <div className="sr-only" data-testid="artifact-detail">
          {tooltipRows.map((row) => (
            <span key={row.label}>{row.label}: {row.value}; </span>
          ))}
        </div>
      </TooltipProvider>
    );
  }

  if (artifactMode === 'blocked') {
    return (
      <Badge variant="secondary" className="gap-1.5">
        <AlertTriangle className="h-3.5 w-3.5" />
        <span>Artifact Blocked</span>
      </Badge>
    );
  }

  return null;
}
