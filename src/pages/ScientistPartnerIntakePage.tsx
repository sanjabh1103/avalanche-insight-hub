import { useMemo, useState } from 'react';
import { Link } from 'react-router-dom';
import { ArrowLeft, CheckCircle2, Download, FileUp, ShieldAlert, UploadCloud } from 'lucide-react';
import { toast } from 'sonner';

import RoleAccessGate from '@/components/RoleAccessGate';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import {
  PARTNER_SOURCE_MANIFEST_FILENAME,
  REQUIRED_PARTNER_EVIDENCE_FILES,
  buildPartnerEvidenceReadinessSummary,
  markdownPartnerEvidenceReadinessSummary,
  type PartnerEvidenceFileInput,
  type PartnerEvidenceReadinessSummary,
} from '@/lib/partnerEvidenceReadiness';

function downloadText(filename: string, content: string, type = 'application/json;charset=utf-8') {
  const blob = new Blob([content], { type });
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement('a');
  anchor.href = url;
  anchor.download = filename;
  anchor.click();
  URL.revokeObjectURL(url);
}

function statusTone(status: string) {
  if (status === 'reviewed' || status === 'valid_manifest') return 'bg-emerald-500/15 text-emerald-300';
  if (status === 'empty') return 'bg-sky-500/15 text-sky-300';
  if (status === 'pending_review') return 'bg-amber-500/15 text-amber-300';
  return 'bg-red-500/15 text-red-200';
}

async function filesToInputs(fileList: FileList | File[]): Promise<PartnerEvidenceFileInput[]> {
  const files = Array.from(fileList);
  return Promise.all(
    files.map(async (file) => ({
      name: file.webkitRelativePath || file.name,
      text: await file.text(),
      sizeBytes: file.size,
      lastModified: file.lastModified,
    })),
  );
}

export default function ScientistPartnerIntakePage() {
  return (
    <div className="min-h-screen bg-background px-4 py-4 text-foreground sm:px-6 lg:px-8">
      <div className="mx-auto max-w-6xl space-y-4">
        <header className="flex flex-col gap-3 rounded-[1.5rem] border border-border/70 bg-card/70 p-4 shadow-2xl shadow-black/20 backdrop-blur-2xl sm:flex-row sm:items-center sm:justify-between">
          <div>
            <div className="text-sm font-semibold uppercase tracking-[0.18em]">Partner Evidence Intake</div>
            <div className="text-xs text-muted-foreground">Browser preflight for Himalayan v3 partner package files</div>
          </div>
          <Button asChild variant="outline" className="rounded-2xl">
            <Link to="/scientist">
              <ArrowLeft className="mr-2 h-4 w-4" />
              Scientist queue
            </Link>
          </Button>
        </header>

        <RoleAccessGate
          allowedRoles={['scientist', 'admin']}
          gateTitle="Scientist Access"
          routeLabel="partner evidence intake session"
          sessionLabel="Scientist Session"
        >
          <PartnerIntakeWorkbench />
        </RoleAccessGate>
      </div>
    </div>
  );
}

function PartnerIntakeWorkbench() {
  const [summary, setSummary] = useState<PartnerEvidenceReadinessSummary | null>(null);
  const [uploadedFileNames, setUploadedFileNames] = useState<string[]>([]);
  const [processing, setProcessing] = useState(false);
  const requiredFiles = useMemo(
    () => [PARTNER_SOURCE_MANIFEST_FILENAME, ...REQUIRED_PARTNER_EVIDENCE_FILES.map((item) => item.filename)],
    [],
  );

  const processFiles = async (fileList: FileList | File[]) => {
    setProcessing(true);
    try {
      const inputs = await filesToInputs(fileList);
      setUploadedFileNames(inputs.map((file) => file.name));
      setSummary(await buildPartnerEvidenceReadinessSummary(inputs));
      toast.success('Partner package preflight complete');
    } catch (error) {
      toast.error(error instanceof Error ? error.message : 'Failed to preflight partner package');
    } finally {
      setProcessing(false);
    }
  };

  return (
    <div className="grid gap-4 lg:grid-cols-[minmax(0,1fr)_380px]">
      <div className="space-y-4">
        <Card className="border border-border/70 bg-card/60 backdrop-blur-xl">
          <CardHeader>
            <CardTitle className="flex items-center gap-2 text-sm uppercase tracking-[0.18em]">
              <UploadCloud className="h-4 w-4 text-emerald-400" />
              Local Package Preflight
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            <div
              className="rounded-2xl border border-dashed border-border/80 bg-black/10 p-5 text-center"
              onDragOver={(event) => {
                event.preventDefault();
              }}
              onDrop={(event) => {
                event.preventDefault();
                if (event.dataTransfer.files.length > 0) {
                  void processFiles(event.dataTransfer.files);
                }
              }}
            >
              <FileUp className="mx-auto h-8 w-8 text-emerald-300" />
              <div className="mt-3 text-sm font-semibold text-foreground">Drop partner files here</div>
              <div className="mt-1 text-xs text-muted-foreground">
                Upload {PARTNER_SOURCE_MANIFEST_FILENAME} plus the ten v3 evidence CSV templates. Files stay in this browser session.
              </div>
              <Input
                type="file"
                multiple
                className="mt-4"
                aria-label="Upload partner evidence package files"
                disabled={processing}
                onChange={(event) => {
                  if (event.currentTarget.files?.length) {
                    void processFiles(event.currentTarget.files);
                  }
                }}
              />
            </div>

            <div className="rounded-xl border border-border/60 bg-black/10 p-3 text-xs text-muted-foreground">
              <div className="mb-2 flex items-center gap-2 font-semibold uppercase tracking-[0.18em] text-foreground">
                <ShieldAlert className="h-4 w-4 text-amber-300" />
                Claim Boundary
              </div>
              This browser preflight checks required file names, exact headers, SHA-256 digests, reviewed-row counts, and synthetic markers. It does not run CLI triage, local holdout validation, SAR promotion, production scoring, or release-gate attestation.
            </div>

            {summary ? (
              <div className="space-y-3">
                <div className="grid gap-2 sm:grid-cols-4">
                  <Metric label="Files" value={`${summary.present_file_count}/${summary.required_file_count}`} />
                  <Metric label="Headers" value={`${summary.header_pass_count}/${REQUIRED_PARTNER_EVIDENCE_FILES.length}`} />
                  <Metric label="Rows" value={summary.total_row_count} />
                  <Metric label="Reviewed" value={summary.reviewed_row_count} />
                </div>
                <div className="rounded-xl border border-border/60 bg-black/10 p-3">
                  <div className="flex flex-wrap items-center justify-between gap-2">
                    <div>
                      <div className="text-[10px] uppercase tracking-[0.18em] text-muted-foreground">Decision</div>
                      <div className="mt-1 break-all font-mono text-xs text-foreground">{summary.decision}</div>
                    </div>
                    <Badge className={`rounded-full border-0 text-[10px] ${summary.blockers.length === 0 ? 'bg-emerald-500/15 text-emerald-300' : 'bg-amber-500/15 text-amber-300'}`}>
                      {summary.blockers.length === 0 ? 'CLI triage ready' : `${summary.blockers.length} blocker(s)`}
                    </Badge>
                  </div>
                </div>
                <div className="grid gap-2 sm:grid-cols-2">
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={() => downloadText('partner-intake-preflight.json', JSON.stringify(summary, null, 2))}
                  >
                    <Download className="mr-2 h-4 w-4" />
                    Export JSON
                  </Button>
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={() => downloadText('partner-intake-preflight.md', markdownPartnerEvidenceReadinessSummary(summary), 'text/markdown;charset=utf-8')}
                  >
                    <Download className="mr-2 h-4 w-4" />
                    Export Markdown
                  </Button>
                </div>
              </div>
            ) : null}
          </CardContent>
        </Card>

        <Card className="border border-border/70 bg-card/60 backdrop-blur-xl">
          <CardHeader>
            <CardTitle className="flex items-center gap-2 text-sm uppercase tracking-[0.18em]">
              <CheckCircle2 className="h-4 w-4 text-emerald-400" />
              File Results
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-2">
            {!summary ? (
              <div className="rounded-lg border border-border/60 bg-black/10 p-3 text-sm text-muted-foreground">
                No package preflight yet. Required files are listed on the right.
              </div>
            ) : summary.files.map((file) => (
              <div key={file.filename} className="rounded-lg border border-border/60 bg-black/10 p-3 text-xs">
                <div className="flex flex-wrap items-start justify-between gap-2">
                  <div className="min-w-0">
                    <div className="font-mono text-foreground">{file.filename}</div>
                    <div className="text-muted-foreground">{file.label}</div>
                  </div>
                  <Badge className={`shrink-0 rounded-full border-0 text-[10px] ${statusTone(file.status)}`}>
                    {file.status.replace(/_/g, ' ')}
                  </Badge>
                </div>
                <div className="mt-2 grid gap-2 text-[10px] text-muted-foreground sm:grid-cols-3">
                  <span>Rows <span className="font-mono text-foreground">{file.rowCount}</span></span>
                  <span>Reviewed <span className="font-mono text-foreground">{file.reviewedRowCount}</span></span>
                  <span>SHA <span className="font-mono text-foreground">{file.sha256 ? `${file.sha256.slice(0, 12)}...` : 'n/a'}</span></span>
                </div>
                {file.blockers.length > 0 ? (
                  <div className="mt-2 space-y-1 text-[10px] text-amber-200">
                    {file.blockers.map((blocker) => <div key={blocker}>- {blocker}</div>)}
                  </div>
                ) : null}
              </div>
            ))}
          </CardContent>
        </Card>
      </div>

      <div className="space-y-4">
        <Card className="border border-border/70 bg-card/60 backdrop-blur-xl">
          <CardHeader>
            <CardTitle className="text-sm uppercase tracking-[0.18em]">Required Package</CardTitle>
          </CardHeader>
          <CardContent className="space-y-2">
            {requiredFiles.map((filename) => (
              <div key={filename} className="flex items-center justify-between gap-2 rounded-lg border border-border/50 bg-black/10 px-2 py-1.5 text-[10px]">
                <span className="min-w-0 break-all font-mono text-foreground">{filename}</span>
                <Badge variant="outline" className="shrink-0 rounded-full text-[9px]">
                  {uploadedFileNames.some((name) => name.endsWith(filename)) ? 'seen' : 'required'}
                </Badge>
              </div>
            ))}
          </CardContent>
        </Card>

        <Card className="border border-border/70 bg-card/60 backdrop-blur-xl">
          <CardHeader>
            <CardTitle className="text-sm uppercase tracking-[0.18em]">Next Use</CardTitle>
          </CardHeader>
          <CardContent className="space-y-2 text-xs text-muted-foreground">
            <p>Export the preflight JSON/Markdown and keep the original partner package unchanged.</p>
            <p>After real partner rows arrive, run the backend CLI triage to produce the authoritative package summary and quality score.</p>
            <p className="rounded-lg border border-border/60 bg-black/10 p-2 font-mono text-[10px] text-foreground">
              production_scoring_allowed=false<br />
              himalayan_accuracy_claim_allowed=false
            </p>
          </CardContent>
        </Card>
      </div>
    </div>
  );
}

function Metric({ label, value }: { label: string; value: string | number }) {
  return (
    <div className="rounded-lg border border-border/60 bg-black/10 p-2">
      <div className="text-[9px] uppercase tracking-[0.18em] text-muted-foreground">{label}</div>
      <div className="font-mono text-sm text-foreground">{value}</div>
    </div>
  );
}
