# Pre-Presentation Freshness Risk Mitigation

Status: 2026-05-27  
Purpose: record the exact hosted-batch freshness mitigation and the safe demo language to use after the refresh.  
Boundary: this proves a fresh Colorado Rockies technical publication artifact. It does not prove official warning authority, validated Himalayan accuracy, promoted SAR, or production-ready detection.

## Result

The main presentation risk was real and has been mitigated.

| Check | Before refresh | After refresh |
|---|---|---|
| Hosted public route | `PRECOMPUTED BATCH - STALE (72h)` | `PRECOMPUTED BATCH - READY (72h)` |
| Browser freshness text | `last batch 6d ago` | `last batch just now` |
| Region | Colorado Rockies | Colorado Rockies |
| Forecast date | 2026-05-20 artifact visible as stale | 2026-05-27 published artifact |
| Forecast run id | `62dbb0f2-e8e9-4f2d-99f5-44b6c753dc3e` | `f0632464-9200-42e0-bc29-c608291f8c26` |
| Proof status | stale in browser | `publication_proof.json` passed |
| Grid / horizon | 20x20 / 72h previous proof | 20x20 / 72h current proof |
| Ready cells | previous proof | 400 / 400 |
| Stale cells | browser warning | 0 |
| Data lineage | prior proof real-derived | `observed_or_derived_real`; synthetic inputs false |

## Command Used

The refresh used the repo's strict same-day publication path and required full-grid proof:

```bash
set -a
source .env
set +a
export SUPABASE_URL="${SUPABASE_URL:-$VITE_SUPABASE_URL}"
.venv/bin/python -m backend.daily_inference \
  --artifact-dir 20260504T070406Z \
  --region-key colorado_rockies \
  --forecast-hours 72 \
  --grid-size 20 \
  --require-same-day-publication \
  --require-full-grid-publication \
  --emit-stage-metrics
```

The command writes hosted Supabase forecast state. Do not rerun it casually; rerun only as the pre-demo freshness action.

## Verification Evidence

| Evidence | Current value |
|---|---|
| Local proof file | `backend/artifacts/20260504T070406Z/publication_proof.json` |
| `proof_status` | `passed` |
| `compute_proof_status` | `passed` |
| `same_day_published_count` | 1 / 1 |
| `full_grid_publication_ready_count` | 1 / 1 |
| `expected_forecast_date` | `2026-05-27` |
| `published_at` | `2026-05-27T14:38:44.748801+00:00` |
| Browser URL checked | `https://avalanche-insight-hub.netlify.app/?freshness_check=20260527T1439` |
| Browser text checked | `Publication state: last batch just now`; `PRECOMPUTED BATCH - READY (72h)` |
| Screenshot | `docs/MVP_V2/07_demo_assets/screenshots/hosted-public-fresh-batch-2026-05-27.png` |

## Must Not Say

| Do not say | Why |
|---|---|
| "Fresh operational forecast" | The refreshed artifact is a technical decision-support publication, not an official forecast service. |
| "Official warning service" | No authority handoff or public warning mandate is established. |
| "Validated Himalayan accuracy" | The fresh batch is Colorado Rockies; Himalayan validation still needs local reviewed evidence and gates. |
| "Promoted SAR" | SAR remains shadow-gated and blocked from production scoring. |
| "Production-ready avalanche detection" | Detection, remote sensing, and promotion gates are not complete. |
| "Users can rely on this for field safety" | The UI itself states it is experimental and not for life-critical decisions. |

## Best Demo Framing

Use this exact framing:

> Hosted decision-support prototype with evidence governance and scientist co-working workflow; Himalayan validation requires local reviewed evidence.

When showing the refreshed public route, say:

> The Colorado Rockies batch is fresh today and proves the publication mechanics: hosted route, 20x20 grid, 72-hour artifact, freshness status, map review, bulletin-style context, uncertainty cues, share/export, and role-gated admin/scientist lanes.

Then immediately add:

> This is not a Himalayan accuracy claim and not an official warning service. The autonomous pipeline can activate without any historical data. Stronger claims would require scientist validation of autonomous pipeline output — not an upfront data handover.

## If The Batch Becomes Stale Again

| Situation | Action | Safe wording |
|---|---|---|
| Browser shows `READY` and `last batch just now/today` | Demo live public route. | "Fresh Colorado technical publication artifact." |
| Browser shows `STALE` or `last batch >24h` | Rerun the same publication command before demo, then recheck browser. | Do not call it fresh until proof passes. |
| Publication proof fails | Keep the hosted route as technical proof only and show the failure reason. | "The prototype is hosted, but today's publication proof did not pass." |
| Admin/scientist credentials are not ready | Show gates only or use prepared screenshots. | "The routes are implemented and gated; signed-in workflow requires prepared demo accounts." |

## External Practice Anchors

| Anchor | How it shapes the demo |
|---|---|
| WMO Impact-Based Forecast and Warning Services | Supports framing the product as decision-support that combines likelihood, severity, impacts, and expert advice without claiming warning authority. |
| EAWS danger scale / avalanche problems / spatial-temporal standards | Supports showing danger level, avalanche problem, aspect/elevation/time context, while keeping the UI "EAWS-style experimental" until local authority review. |
| RAvaFcast GMD 2024 | Supports the future roadmap: station classification, interpolation, aggregation, and station-density limits before regional warning-region claims. |
| NHESS 2022 dry-snow danger-level work | Supports the label-quality warning: public bulletins alone are not enough; reviewed or tidy labels are needed before local accuracy claims. |
