import { GitCompareArrows, MapPin, ShieldAlert, Snowflake } from 'lucide-react';
import { Badge } from '@/components/ui/badge';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import {
  PIR_PANJAL_POC_EVIDENCE,
  PIR_PANJAL_POC_REGION_KEY,
  type PirPanjalPocEvidence,
} from '@/lib/pirPanjalPocEvidence';
import { useSnowpackRuns } from '@/hooks/useSnowpackRuns';

function formatCoordinate(value: number): string {
  return value.toFixed(6);
}

function Metric({ label, value, detail }: { label: string; value: string; detail?: string }) {
  return (
    <div className="rounded-md border border-border/50 bg-black/10 p-2">
      <div className="text-[9px] uppercase tracking-[0.16em] text-muted-foreground">{label}</div>
      <div className="mt-1 font-mono text-sm text-foreground">{value}</div>
      {detail ? <div className="mt-0.5 text-[9px] text-muted-foreground">{detail}</div> : null}
    </div>
  );
}

function ScopeBadges({ evidence }: { evidence: PirPanjalPocEvidence }) {
  return (
    <div className="flex flex-wrap gap-1.5">
      <Badge className="rounded-full border-0 bg-sky-500/15 text-[9px] text-sky-300">
        {evidence.scope.elevationRange}
      </Badge>
      <Badge className="rounded-full border-0 bg-sky-500/15 text-[9px] text-sky-300">
        {evidence.scope.horizonHours}h · {evidence.scope.ensembleMembers} member
      </Badge>
      {evidence.scope.problemTypes.map((problem) => (
        <Badge key={problem} className="rounded-full border-0 bg-amber-500/15 text-[9px] text-amber-300">
          {problem}
        </Badge>
      ))}
    </div>
  );
}

export default function PirPanjalPocEvidenceCard({ live = false }: { live?: boolean }) {
  const evidence = PIR_PANJAL_POC_EVIDENCE;
  const { runs: verifiedRuns, loading: liveLoading } = useSnowpackRuns({
    regionKey: PIR_PANJAL_POC_REGION_KEY,
    pocModeOnly: true,
    verifiedOnly: true,
    enabled: live,
    limit: 1,
  });
  const verifiedRun = verifiedRuns[0] ?? null;
  const currentVerifiedRun = evidence.provenance.evidenceStatus === 'current_verified_mapping'
    ? verifiedRun
    : null;

  return (
    <Card data-testid="pir-panjal-poc-evidence-card" className="border border-amber-500/30 bg-card/70 backdrop-blur-xl">
      <CardHeader className="p-3 pb-1">
        <div className="flex items-start justify-between gap-2">
          <CardTitle className="flex items-center gap-1.5 text-xs uppercase tracking-[0.2em] text-muted-foreground">
            <Snowflake className="h-3 w-3 text-sky-300" />
            Pir Panjal POC — {currentVerifiedRun ? 'verified run reference · snapshot panels' : 'historical snapshot · corrected rerun required'}
          </CardTitle>
          <Badge className="shrink-0 rounded-full border-0 bg-amber-500/15 text-[9px] text-amber-300">
            Pipeline proof only
          </Badge>
        </div>
        <div className="mt-2 flex flex-wrap gap-1.5">
          <Badge className="rounded-full border-0 bg-sky-500/15 text-[9px] text-sky-300">
            Verified hosted candidate · corrected v2 forcing
          </Badge>
          <Badge className="rounded-full border-0 bg-violet-500/15 text-[9px] text-violet-300">
            Retrospective · controlled use
          </Badge>
        </div>
      </CardHeader>
      <CardContent className="space-y-3 p-3 pt-2">
        {live ? (
          <div
            data-testid="pir-panjal-poc-live-state"
            className="rounded-lg border border-sky-500/25 bg-sky-500/5 p-2 text-[9px] text-sky-100/80"
          >
            {liveLoading ? 'Checking for a current verified live run…' : currentVerifiedRun ? (
              <>
                Verified run reference: <span className="font-mono break-all">{currentVerifiedRun.run_id}</span> ·
                {' '}status {currentVerifiedRun.status}. The panels below reflect the corrected verified hosted bundle snapshot;
                raw outputs remain private.
              </>
            ) : (
              'The corrected v2 hosted run has passed both the producer and independent consumer release gates. The snapshot panels below reflect this verified bundle; raw outputs remain private.'
            )}
          </div>
        ) : null}
        <div className="space-y-1 text-[10px] text-muted-foreground">
          <div className="flex items-center gap-1.5 text-foreground">
            <MapPin className="h-3 w-3 text-sky-300" />
            <span>{evidence.site.siteId}</span>
          </div>
          <div>
            {formatCoordinate(evidence.site.latitude)}, {formatCoordinate(evidence.site.longitude)} · {evidence.site.elevationM} m ·
            {' '}{evidence.site.slopeDeg}° slope · {evidence.site.aspectDeg}° {evidence.site.aspectLabel} aspect
          </div>
          <div>
            Retrospective window: <span className="font-mono">{evidence.evaluationWindow.start}</span> →{' '}
            <span className="font-mono">{evidence.evaluationWindow.end}</span>
          </div>
        </div>

        <ScopeBadges evidence={evidence} />

        <section className="space-y-2 rounded-lg border border-emerald-500/20 bg-emerald-500/5 p-2.5" aria-label="Forcing resolution and input quality">
          <div className="text-[10px] font-semibold uppercase tracking-[0.18em] text-emerald-200">
            Forcing and resolution disclosure
          </div>
          <div className="grid grid-cols-2 gap-1.5">
            <Metric label="Hourly samples" value={String(evidence.forcingQuality.sampleCount)} />
            <Metric label="Source samples" value={String(evidence.forcingQuality.sourceSampleCount)} detail={`${evidence.forcingQuality.warmupHours}h warm-up included`} />
            <Metric label="Target computational scale" value={`${evidence.forcingQuality.targetGridM / 1000} km`} />
            <Metric label="Nominal GFS surface scale" value={`~${evidence.forcingQuality.sourceNativeResolutionM / 1000} km`} />
            <Metric label="Effective information scale" value={`~${evidence.forcingQuality.effectiveInformationScaleM / 1000} km`} />
            <Metric label="Direct snowfall" value={`${evidence.forcingQuality.directSnowfallAvailableSamples} available`} detail="null preserved; no zero fill" />
            <Metric label="Source snow depth" value={`${evidence.forcingQuality.sourceSnowDepthAvailableSamples} samples`} detail="QA only; not SNOWPACK HS" />
          </div>
          <div className="text-[9px] text-emerald-100/70">
            The 3 km value is a computational target only; it is not a 3 km meteorological-information or skill claim.
          </div>
          <div className="text-[9px] text-emerald-100/70">
            Native log warnings: none. Precipitation is explicitly re-accumulated by pinned MeteoIO over 3,600 seconds.
          </div>
        </section>

        <section className="space-y-2 rounded-lg border border-sky-500/20 bg-sky-500/5 p-2.5" aria-label="SNOWPACK candidate profile snapshot">
          <div className="flex items-center gap-1.5 text-[10px] font-semibold uppercase tracking-[0.18em] text-sky-200">
            <Snowflake className="h-3 w-3" /> SNOWPACK native profile snapshot
          </div>
          <div className="grid grid-cols-2 gap-1.5">
            <Metric label="Profile layers" value={String(evidence.nativeProfile.layerCount)} />
            <Metric label="Snow height" value={`${evidence.nativeProfile.snowHeightM.toFixed(3)} m`} />
            <Metric label="Bulk density" value={`${evidence.nativeProfile.bulkDensityKgM3.toFixed(1)} kg/m³`} />
            <Metric
              label="Profile index"
              value={evidence.nativeProfile.stabilityIndex.toFixed(2)}
              detail="unvalidated native index"
            />
            <Metric label="Weak-layer shear" value={`${evidence.nativeProfile.weakLayerShearStrengthKpa.toFixed(2)} kPa`} />
            <Metric label="Weak-layer grain" value={evidence.nativeProfile.weakLayerGrainType} />
            <Metric label="Temperature gradient" value={`${evidence.nativeProfile.temperatureGradientPerM.toFixed(2)} K/m`} />
            <Metric label="Liquid water" value={`${evidence.nativeProfile.liquidWaterContentPct.toFixed(1)}%`} />
          </div>
          <div className="text-[9px] text-muted-foreground">
            Profile timestamp: <span className="font-mono">{evidence.nativeProfile.profileDate}</span>
          </div>
        </section>

        <section className="space-y-2 rounded-lg border border-violet-500/20 bg-violet-500/5 p-2.5" aria-label="RF comparison baseline snapshot">
          <div className="flex items-center gap-1.5 text-[10px] font-semibold uppercase tracking-[0.18em] text-violet-200">
            <GitCompareArrows className="h-3 w-3" /> RF comparison baseline snapshot
          </div>
          <div className="grid grid-cols-2 gap-1.5">
            <Metric label="Comparison status" value={evidence.rfComparison.status} detail="direct snowfall unavailable" />
          </div>
          <div className="text-[9px] text-muted-foreground">
            {evidence.rfComparison.reason}
          </div>
        </section>

        <div className="space-y-1 text-[9px] text-muted-foreground">
          <div className="font-semibold uppercase tracking-[0.16em] text-foreground">Provenance</div>
          <div>Run ID: <span className="font-mono break-all">{evidence.provenance.runId}</span></div>
          <div>Candidate result SHA-256: <span className="font-mono break-all">{evidence.provenance.candidateResultSha256}</span></div>
          <div>Forcing: {evidence.provenance.forcingSource} · {evidence.provenance.forcingModel}</div>
          <div>Toolchain: {evidence.provenance.binaryVersion} · {evidence.provenance.nativeIdentity}</div>
          <div>Hosted image ID: <span className="font-mono break-all">{evidence.provenance.imageId}</span></div>
          <div>Image archive SHA-256: <span className="font-mono break-all">{evidence.provenance.imageArchiveSha256}</span></div>
          <div>SMET SHA-256: <span className="font-mono break-all">{evidence.provenance.smetSha256}</span></div>
        </div>

        <div className="space-y-1.5 rounded-lg border border-amber-500/25 bg-amber-500/5 p-2.5 text-[9px] text-amber-100/80">
          <div className="flex items-center gap-1.5 font-semibold uppercase tracking-[0.16em] text-amber-200">
            <ShieldAlert className="h-3 w-3" /> Boundaries
          </div>
          <ul className="list-disc space-y-1 pl-4">
            {evidence.limitations.map((limitation) => <li key={limitation}>{limitation}</li>)}
          </ul>
          <div className="font-semibold text-amber-200">Official-warning eligible: no</div>
        </div>
      </CardContent>
    </Card>
  );
}
