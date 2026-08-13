import { useState } from 'react';
import { Link } from 'react-router-dom';
import {
  Brain,
  Gauge,
  AlertTriangle,
  GitBranch,
  BookOpen,
  CheckCircle2,
  XCircle,
  Copy,
  Check,
  ArrowRight,
} from 'lucide-react';
import { Card, CardContent } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Tooltip, TooltipContent, TooltipTrigger } from '@/components/ui/tooltip';
import CitationBlock from '@/components/CitationBlock';
import DataSourceAttribution from '@/components/DataSourceAttribution';
import { RISK_COLORS, RISK_LABELS } from '@/lib/constants';

const DATA_SOURCES = [
  { name: 'Open-Meteo', url: 'https://open-meteo.com/' },
  { name: 'EnviDat (WSL)', url: 'https://www.envidat.ch/' },
  { name: 'OpenStreetMap', url: 'https://www.openstreetmap.org/' },
  { name: 'NASA GIBS', url: 'https://earthdata.nasa.gov/gibs' },
];

const SHAP_FEATURES = [
  { rank: 1, feature: 'elevation_th', meanAbs: 0.078, interpretation: 'Higher elevation → higher danger' },
  { rank: 2, feature: 'HN72_24', meanAbs: 0.046, interpretation: '72h new snow height → loading driver' },
  { rank: 3, feature: 'HN24_7d', meanAbs: 0.035, interpretation: '7-day new snow → persistent weak layer' },
  { rank: 4, feature: 'Pen_depth', meanAbs: 0.026, interpretation: 'Penetration depth → snowpack stability' },
  { rank: 5, feature: 'HN24', meanAbs: 0.026, interpretation: '24h new snow → immediate loading' },
];

const CONFUSION_MATRIX = [
  [621, 70, 0, 0],
  [51, 960, 134, 0],
  [0, 129, 798, 14],
  [0, 0, 21, 38],
];

const LIMITATIONS = [
  {
    title: 'Synthetic data boundary',
    detail: 'Not operational warning. System is a decision-support prototype rendering published technical artifacts.',
  },
  {
    title: 'Regional bias',
    detail: 'Trained exclusively on Swiss Alps data. Transferability to Himalayan, Andean, or other conditions is unvalidated.',
  },
  {
    title: 'Live grid proxy; candidate SNOWPACK POC',
    detail: 'The live forecast grid remains proxy-derived. A separate SNOWPACK native profile exists only as a retrospective, pipeline-proof candidate POC and is not connected to live risk or warning output.',
  },
  {
    title: 'No sub-level danger',
    detail: 'Maissen et al. (2024) sub-level danger prediction not implemented.',
  },
  {
    title: 'No event-ratio validation',
    detail: 'Pérez-Guillén et al. (2025) bin-wise event-ratio validation not yet computed on this model.',
  },
  {
    title: 'Class imbalance',
    detail: 'Class 4 (High) has only 158 samples (5.4%). Model may underperform on rare High-danger events.',
  },
];

const REPRO_COMMANDS = [
  { label: 'Validate data', cmd: 'python3 -m backend.reproduction.swiss_ravafcast.cli validate-data --manifest backend/data/swiss_envidat/swiss_ravafcast_data_manifest.json --output validation_report.json' },
  { label: 'Train model', cmd: 'python3 -m backend.reproduction.swiss_ravafcast.cli train-rf4 --manifest backend/data/swiss_envidat/swiss_ravafcast_data_manifest.json --output rf4_result.json --feature-set auto_numeric_current' },
  { label: 'Audit GPxyz', cmd: 'python3 -m backend.reproduction.swiss_ravafcast.cli audit-gpxyz --manifest backend/data/swiss_envidat/swiss_ravafcast_data_manifest.json --output gpxyz_report.json' },
  { label: 'Aggregate', cmd: 'python3 -m backend.reproduction.swiss_ravafcast.cli aggregate-elev-simple --rf4-result rf4_result.json --output aggregation_result.json' },
  { label: 'Summarize', cmd: 'python3 -m backend.reproduction.swiss_ravafcast.cli summarize-reproduction --validation-report validation_report.json --rf4-result rf4_result.json --gpxyz-report gpxyz_report.json --aggregation-result aggregation_result.json --output reproduction_summary.json' },
];

const CITATIONS = [
  {
    citation: 'Pérez-Guillén, C., et al. (2024). EnviDat RF2 dataset. Swiss Federal Institute for Forest, Snow and Landscape Research (WSL).',
    bibtex: `@dataset{perez_guillen_2024_envidat,
  author = {Pérez-Guillén, C. and others},
  title = {EnviDat RF2 Dataset},
  publisher = {WSL},
  year = {2024},
  url = {https://www.envidat.ch/}
}`,
  },
  {
    citation: 'Pérez-Guillén, C., et al. (2025). Physics-informed machine learning for avalanche forecasting. Natural Hazards and Earth System Sciences (NHESS).',
    bibtex: `@article{perez_guillen_2025_physics,
  author = {Pérez-Guillén, C. and others},
  title = {Physics-informed machine learning for avalanche forecasting},
  journal = {Natural Hazards and Earth System Sciences},
  year = {2025}
}`,
  },
  {
    citation: 'Mitchell, M., et al. (2019). Model Cards for Model Reporting. FAT 2019.',
    bibtex: `@inproceedings{mitchell_2019_modelcards,
  author = {Mitchell, M. and others},
  title = {Model Cards for Model Reporting},
  booktitle = {FAT},
  year = {2019}
}`,
  },
  {
    citation: 'Lundberg, S., & Lee, S. (2017). A Unified Approach to Interpreting Model Predictions (SHAP). NeurIPS 2017.',
    bibtex: `@inproceedings{lundberg_2017_shap,
  author = {Lundberg, S. and Lee, S.},
  title = {A Unified Approach to Interpreting Model Predictions},
  booktitle = {NeurIPS},
  year = {2017}
}`,
  },
];

function Section({ id, icon: Icon, title, children }: { id: string; icon: typeof Brain; title: string; children: React.ReactNode }) {
  return (
    <section id={id} className="scroll-mt-24">
      <div className="mb-4 flex items-center gap-2.5">
        <div className="flex h-9 w-9 items-center justify-center rounded-xl bg-emerald-500/10 border border-emerald-500/20">
          <Icon className="h-4.5 w-4.5 text-emerald-400" />
        </div>
        <h2 className="text-xl font-semibold tracking-tight text-foreground">{title}</h2>
      </div>
      {children}
    </section>
  );
}

function MetricChip({ label, value, tooltip }: { label: string; value: string; tooltip?: string }) {
  return (
    <Tooltip>
      <TooltipTrigger asChild>
        <div className="inline-flex items-center gap-1.5 rounded-lg border border-border/50 bg-secondary/20 px-2.5 py-1.5 cursor-help">
          <span className="text-[10px] font-mono uppercase tracking-[0.15em] text-muted-foreground">{label}</span>
          <span className="text-sm font-mono font-semibold text-foreground">{value}</span>
        </div>
      </TooltipTrigger>
      {tooltip && <TooltipContent>{tooltip}</TooltipContent>}
    </Tooltip>
  );
}

export default function MethodsPage() {
  const [copiedCmd, setCopiedCmd] = useState<number | null>(null);

  const copyCommand = async (idx: number, cmd: string) => {
    try {
      await navigator.clipboard.writeText(cmd);
      setCopiedCmd(idx);
      setTimeout(() => setCopiedCmd(null), 2000);
    } catch {
      // clipboard not available
    }
  };

  return (
    <div className="mx-auto max-w-[1200px] px-4 py-8 sm:px-6 lg:px-8">
      {/* Header */}
      <div className="mb-8">
        <h1 className="mb-2 text-3xl font-bold tracking-tight text-foreground">Methods & Validation</h1>
        <p className="max-w-2xl text-sm leading-relaxed text-muted-foreground">
          Model architecture, calibration, validation metrics, and limitations for the Random Forest 4 (RF4)
          avalanche danger classifier. All content is sourced from the reproducible model card.
        </p>
      </div>

      {/* Quick navigation */}
      <div className="mb-10 flex flex-wrap gap-2">
        {[
          { href: '#architecture', label: 'Architecture' },
          { href: '#calibration', label: 'Calibration' },
          { href: '#validation', label: 'Validation' },
          { href: '#limitations', label: 'Limitations' },
          { href: '#reproducibility', label: 'Reproducibility' },
          { href: '#citations', label: 'Citations' },
        ].map((link) => (
          <a
            key={link.href}
            href={link.href}
            className="rounded-lg border border-border/50 bg-secondary/20 px-3 py-1.5 text-xs font-medium text-muted-foreground transition-colors hover:border-emerald-500/30 hover:text-foreground"
          >
            {link.label}
          </a>
        ))}
      </div>

      <div className="space-y-12">
        {/* Section 1: Architecture */}
        <Section id="architecture" icon={Brain} title="Model Architecture">
          <Card className="border-border/60 bg-card/40">
            <CardContent className="p-6">
              <div className="grid gap-6 md:grid-cols-2">
                <div className="space-y-3">
                  <div>
                    <span className="text-xs font-mono uppercase tracking-[0.15em] text-muted-foreground">Type</span>
                    <p className="text-sm text-foreground">Random Forest classifier (scikit-learn)</p>
                  </div>
                  <div>
                    <span className="text-xs font-mono uppercase tracking-[0.15em] text-muted-foreground">Trees</span>
                    <p className="text-sm text-foreground">500 estimators</p>
                  </div>
                  <div>
                    <span className="text-xs font-mono uppercase tracking-[0.15em] text-muted-foreground">Calibration</span>
                    <p className="text-sm text-foreground">Isotonic regression (per-class, one-vs-rest)</p>
                  </div>
                  <div>
                    <span className="text-xs font-mono uppercase tracking-[0.15em] text-muted-foreground">Features</span>
                    <p className="text-sm text-foreground">74 numeric (auto_numeric_current, leakage-guarded)</p>
                  </div>
                </div>
                <div className="space-y-3">
                  <div>
                    <span className="text-xs font-mono uppercase tracking-[0.15em] text-muted-foreground">Training data</span>
                    <p className="text-sm text-foreground">EnviDat RF2 dataset — 11,741 samples (train: 5,871, cal: 2,935, test: 2,935)</p>
                  </div>
                  <div>
                    <span className="text-xs font-mono uppercase tracking-[0.15em] text-muted-foreground">Region</span>
                    <p className="text-sm text-foreground">Swiss Alps (WGS84, ~46.0–47.7°N, 5.9–10.5°E)</p>
                  </div>
                  <div>
                    <span className="text-xs font-mono uppercase tracking-[0.15em] text-muted-foreground">Temporal range</span>
                    <p className="text-sm text-foreground">Winter 2017/18 – 2020/21</p>
                  </div>
                  <div>
                    <span className="text-xs font-mono uppercase tracking-[0.15em] text-muted-foreground">Labels</span>
                    <p className="text-sm text-foreground">4-class avalanche danger (1=Low, 2=Moderate, 3=Considerable, 4=High)</p>
                  </div>
                </div>
              </div>

              {/* SHAP feature importance */}
              <div className="mt-6">
                <h3 className="mb-3 text-sm font-semibold text-foreground">Top 5 SHAP Feature Importance (TreeSHAP)</h3>
                <div className="overflow-x-auto">
                  <table className="w-full text-sm">
                    <thead>
                      <tr className="border-b border-border/40 text-left text-xs uppercase tracking-[0.12em] text-muted-foreground">
                        <th className="py-2 pr-4">Rank</th>
                        <th className="py-2 pr-4">Feature</th>
                        <th className="py-2 pr-4">Mean |SHAP|</th>
                        <th className="py-2">Interpretation</th>
                      </tr>
                    </thead>
                    <tbody>
                      {SHAP_FEATURES.map((f) => (
                        <tr key={f.rank} className="border-b border-border/20">
                          <td className="py-2.5 pr-4 font-mono text-muted-foreground">{f.rank}</td>
                          <td className="py-2.5 pr-4 font-mono text-foreground">{f.feature}</td>
                          <td className="py-2.5 pr-4 font-mono text-emerald-400">{f.meanAbs.toFixed(3)}</td>
                          <td className="py-2.5 text-muted-foreground">{f.interpretation}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
                <p className="mt-2 text-xs text-muted-foreground">
                  Method: TreeSHAP (SHAP values computed on 500 test samples, 74 features)
                </p>
              </div>
            </CardContent>
          </Card>
        </Section>

        {/* Section 2: Calibration */}
        <Section id="calibration" icon={Gauge} title="Calibration">
          <Card className="border-border/60 bg-card/40">
            <CardContent className="p-6">
              <div className="flex flex-wrap gap-3 mb-6">
                <MetricChip label="Method" value="Isotonic" tooltip="Per-class one-vs-rest isotonic regression" />
                <MetricChip label="Cal rows" value="2,935" />
                <MetricChip label="ECE reduction" value="67%" tooltip="Expected Calibration Error reduction after isotonic calibration" />
              </div>

              <div className="grid gap-6 md:grid-cols-2">
                <div>
                  <h3 className="mb-3 text-sm font-semibold text-foreground">Calibration Metrics</h3>
                  <div className="overflow-x-auto">
                    <table className="w-full text-sm">
                      <thead>
                        <tr className="border-b border-border/40 text-left text-xs uppercase tracking-[0.12em] text-muted-foreground">
                          <th className="py-2 pr-4">Metric</th>
                          <th className="py-2 pr-4">Uncalibrated</th>
                          <th className="py-2">Calibrated</th>
                        </tr>
                      </thead>
                      <tbody>
                        <tr className="border-b border-border/20">
                          <td className="py-2.5 pr-4 text-foreground">
                            <Tooltip>
                              <TooltipTrigger asChild><span className="cursor-help border-b border-dotted border-muted-foreground">Brier score</span></TooltipTrigger>
                              <TooltipContent>Lower is better. Measures mean squared prediction error.</TooltipContent>
                            </Tooltip>
                          </td>
                          <td className="py-2.5 pr-4 font-mono text-amber-400">0.177</td>
                          <td className="py-2.5 font-mono text-emerald-400">0.157</td>
                        </tr>
                        <tr className="border-b border-border/20">
                          <td className="py-2.5 pr-4 text-foreground">
                            <Tooltip>
                              <TooltipTrigger asChild><span className="cursor-help border-b border-dotted border-muted-foreground">ECE</span></TooltipTrigger>
                              <TooltipContent>Expected Calibration Error. Lower is better.</TooltipContent>
                            </Tooltip>
                          </td>
                          <td className="py-2.5 pr-4 font-mono text-amber-400">0.126</td>
                          <td className="py-2.5 font-mono text-emerald-400">0.041</td>
                        </tr>
                      </tbody>
                    </table>
                  </div>
                </div>
                <div>
                  <h3 className="mb-3 text-sm font-semibold text-foreground">Thresholding</h3>
                  <p className="text-sm leading-relaxed text-muted-foreground">
                    Danger level thresholds are determined using <strong className="text-foreground">data-driven Youden/PSS optimization</strong>,
                    not a fixed threshold. The Peirce Skill Score (PSS) is used as the primary gate metric.
                  </p>
                  <div className="mt-3 flex flex-wrap gap-2">
                    <Badge className="bg-emerald-500/15 text-emerald-300 border-emerald-500/20">PSS gate: pass</Badge>
                    <Badge className="bg-emerald-500/15 text-emerald-300 border-emerald-500/20">Brier &lt; 0.15</Badge>
                  </div>
                </div>
              </div>
            </CardContent>
          </Card>
        </Section>

        {/* Section 3: Validation */}
        <Section id="validation" icon={CheckCircle2} title="Validation">
          <Card className="border-border/60 bg-card/40">
            <CardContent className="p-6">
              <div className="flex flex-wrap gap-3 mb-6">
                <MetricChip label="Accuracy" value="89.37%" />
                <MetricChip label="Macro F1" value="0.747" />
                <MetricChip label="PSS" value="0.51" tooltip="Peirce Skill Score — measures classification skill above random chance" />
                <MetricChip label="Class 4 F1" value="0.349" tooltip="F1 score for High danger class — known weakness" />
                <MetricChip label="Class 4 Recall" value="0.449" />
              </div>

              <h3 className="mb-3 text-sm font-semibold text-foreground">Confusion Matrix (Test Set, n=2,935)</h3>
              <div className="overflow-x-auto">
                <table className="text-sm">
                  <thead>
                    <tr>
                      <th className="px-3 py-2 text-left text-xs uppercase tracking-[0.12em] text-muted-foreground">Actual \ Predicted</th>
                      {[1, 2, 3, 4].map((p) => (
                        <th key={p} className="px-3 py-2 text-center text-xs">
                          <span className="inline-flex items-center gap-1">
                            <span className="h-2.5 w-2.5 rounded-sm" style={{ backgroundColor: RISK_COLORS[p] }} />
                            {RISK_LABELS[p]}
                          </span>
                        </th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {CONFUSION_MATRIX.map((row, i) => (
                      <tr key={i}>
                        <td className="px-3 py-2 text-xs">
                          <span className="inline-flex items-center gap-1">
                            <span className="h-2.5 w-2.5 rounded-sm" style={{ backgroundColor: RISK_COLORS[i + 1] }} />
                            {RISK_LABELS[i + 1]}
                          </span>
                        </td>
                        {row.map((cell, j) => (
                          <td
                            key={j}
                            className={`px-3 py-2 text-center font-mono ${
                              i === j
                                ? 'bg-emerald-500/10 text-emerald-300 font-semibold'
                                : cell > 0
                                  ? 'bg-amber-500/5 text-amber-300/80'
                                  : 'text-muted-foreground/30'
                            }`}
                          >
                            {cell}
                          </td>
                        ))}
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              <div className="mt-3 flex items-start gap-2 rounded-lg border border-amber-500/15 bg-amber-500/5 px-3 py-2.5">
                <AlertTriangle className="mt-0.5 h-3.5 w-3.5 shrink-0 text-amber-400" />
                <p className="text-xs leading-relaxed text-muted-foreground">
                  <strong className="text-amber-400">False negatives on Class 4 (High):</strong> 21 of 59 High-danger days
                  were predicted as Considerable — a potentially dangerous underestimation. This is a known limitation
                  of the current model.
                </p>
              </div>
            </CardContent>
          </Card>
        </Section>

        {/* Section 4: Limitations */}
        <Section id="limitations" icon={AlertTriangle} title="Limitations">
          <div className="grid gap-3 md:grid-cols-2">
            {LIMITATIONS.map((lim) => (
              <Card key={lim.title} className="border-amber-500/15 bg-amber-500/[0.03]">
                <CardContent className="p-4">
                  <div className="flex items-start gap-2.5">
                    <XCircle className="mt-0.5 h-4 w-4 shrink-0 text-amber-400/70" />
                    <div>
                      <h4 className="text-sm font-semibold text-foreground">{lim.title}</h4>
                      <p className="mt-1 text-xs leading-relaxed text-muted-foreground">{lim.detail}</p>
                    </div>
                  </div>
                </CardContent>
              </Card>
            ))}
          </div>
        </Section>

        {/* Section 5: Reproducibility */}
        <Section id="reproducibility" icon={GitBranch} title="Reproducibility">
          <Card className="border-border/60 bg-card/40">
            <CardContent className="p-6">
              <p className="mb-4 text-sm text-muted-foreground">
                All model training, SHAP computation, and feature auditing can be reproduced using the CLI commands below.
                Artifacts are stored in <code className="rounded bg-secondary/40 px-1.5 py-0.5 font-mono text-xs text-foreground">backend/reproduction/artifacts/</code>.
              </p>
              <div className="space-y-3">
                {REPRO_COMMANDS.map((cmd, idx) => (
                  <div key={idx} className="flex items-center gap-3 rounded-xl border border-border/50 bg-secondary/20 px-4 py-3">
                    <span className="shrink-0 text-xs font-mono uppercase tracking-[0.12em] text-muted-foreground">{cmd.label}</span>
                    <code className="flex-1 overflow-x-auto font-mono text-sm text-foreground">{cmd.cmd}</code>
                    <Button
                      variant="ghost"
                      size="icon"
                      className="h-8 w-8 shrink-0 rounded-lg"
                      onClick={() => copyCommand(idx, cmd.cmd)}
                      aria-label={`Copy ${cmd.label} command`}
                    >
                      {copiedCmd === idx ? <Check className="h-3.5 w-3.5 text-emerald-400" /> : <Copy className="h-3.5 w-3.5" />}
                    </Button>
                  </div>
                ))}
              </div>
            </CardContent>
          </Card>
        </Section>

        {/* Section 6: Citations */}
        <Section id="citations" icon={BookOpen} title="Citations">
          <div className="space-y-3">
            {CITATIONS.map((cite, idx) => (
              <CitationBlock key={idx} citation={cite.citation} bibtex={cite.bibtex} />
            ))}
          </div>

          {/* Data sources */}
          <div className="mt-8">
            <h3 className="mb-3 text-sm font-semibold text-foreground">Data Source Attribution</h3>
            <DataSourceAttribution sources={DATA_SOURCES} />
          </div>
        </Section>

        {/* CTA */}
        <div className="flex flex-col items-center gap-3 rounded-2xl border border-border/60 bg-card/40 px-6 py-8 text-center">
          <p className="text-sm text-muted-foreground">Ready to explore the forecast map?</p>
          <Button asChild className="gap-2 rounded-xl bg-emerald-500 text-black hover:bg-emerald-400">
            <Link to="/explore">
              Open Predictions Explorer
              <ArrowRight className="h-4 w-4" />
            </Link>
          </Button>
        </div>
      </div>
    </div>
  );
}
