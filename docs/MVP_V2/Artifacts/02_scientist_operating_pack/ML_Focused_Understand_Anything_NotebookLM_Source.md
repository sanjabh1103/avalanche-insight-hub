# ML-Focused Understand Anything NotebookLM Upload Source

## Topic

Avalanche Insight Hub MVP V2: database structure, machine-learning model lanes, European/SAR research evidence, Himalayan partner evidence gates, and validation boundaries, using the ML-focused Understand Anything pass.

## Purpose

This source packet gives NotebookLM enough grounded material to create a beginner-friendly technical teaching deck. It explains how the current avalanche prediction system is organized, what machine-learning lanes are implemented or gated, why European research improves method discipline, and what Himalayan evidence is still required before local accuracy claims can advance.

It also teaches avalanche danger prediction as a staged pipeline: first classify danger from reviewed features, then spatially interpolate danger and uncertainty, then aggregate outputs by elevation band and warning region.

The target audience is mixed: Sanjay team members, customer stakeholders, avalanche scientists, and technical reviewers who need a single readable source for Deck 6-style explanation.

## Safety Boundary

This is a documentation and teaching source. It does not change app UI, models, Supabase data, deployments, GPU jobs, SAR promotion, or production scoring. It must keep these claim locks visible:

- `production_scoring_allowed=false`
- `himalayan_accuracy_claim_allowed=false`
- Understand Anything graphs are structural codebase evidence, not accuracy proof.
- European and Swiss research improves methodology and validation discipline, but it does not prove Himalayan accuracy without reviewed local evidence.
- SAR remains shadow-gated and outside public scoring until its own gates pass.
- The Himalayan partner workflow is not fully UI-driven today; it is currently CSV, source-manifest, and CLI based with scientist review.
- The three-stage pipeline framing is a teaching structure and validation discipline, not a shortcut around local evidence gates.
- Nano Banana Pro or newer image-generation visuals are explanatory deck assets only; generated visuals are not scientific evidence.

## Current Reference Baseline

The current ML-focused Understand Anything pass produced these durable artifacts:

| Artifact | Path | Use in this source |
|---|---|---|
| Knowledge graph | `/Users/sanjayb/avalanche-insight-hub/.understand-anything/knowledge-graph.json` | Structural graph: files, functions, pipelines, and ML/backend layers. |
| Domain graph | `/Users/sanjayb/avalanche-insight-hub/.understand-anything/domain-graph.json` | Domain map: domains, flows, and steps. |
| Fingerprints | `/Users/sanjayb/avalanche-insight-hub/.understand-anything/fingerprints.json` | File fingerprint inventory for the analysis pass. |
| Metadata | `/Users/sanjayb/avalanche-insight-hub/.understand-anything/meta.json` | Analysis timestamp, commit hash, version, and analyzed file count. |
| Understand ignore policy | `/Users/sanjayb/avalanche-insight-hub/.understand-anything/.understandignore` | Documents that generated outputs and raw/heavy data were excluded from the first ML-model graph. |
| Deck 6 transcript | `/Users/sanjayb/avalanche-insight-hub/docs/MVP_V2/Artifacts/01_deck_pack/avalanche-insight-hub-deck-6-ml-understanding-transcript.md` | Plain-English source for the current explanation deck. |
| Deck 6 HTML | `/Users/sanjayb/avalanche-insight-hub/docs/MVP_V2/Artifacts/01_deck_pack/avalanche-insight-hub-deck-6-ml-understanding.html` | Rendered local deck review artifact. |
| Deck 6 PDF | `/Users/sanjayb/avalanche-insight-hub/docs/MVP_V2/Artifacts/01_deck_pack/avalanche-insight-hub-deck-6-ml-understanding.pdf` | Durable review/export artifact. |
| QA summary | `/Users/sanjayb/avalanche-insight-hub/docs/MVP_V2/Artifacts/01_deck_pack/QA_SUMMARY.md` | Viewport and output validation evidence. |
| Screenshots | `/Users/sanjayb/avalanche-insight-hub/docs/MVP_V2/Artifacts/01_deck_pack/assets/screenshots/ua-*.png` | Durable visual evidence captured from the local Understand Anything dashboard. |

Key graph facts from current artifacts:

```json
{
  "knowledge_graph": {"nodes": 2045, "edges": 4015, "layers": 10},
  "domain_graph": {
    "nodes": 50,
    "edges": 51,
    "types": {"domain": 5, "flow": 10, "step": 35}
  }
}
```

Current Deck 6 validation baseline:

```text
Deck 6 - ML Understanding
slide count: 15
pdf pages: 15
viewport QA: pass at 1920x1080, 1280x720, 768x1024, and 390x844
```

Visual generation baseline:

```text
Preferred visual model in NotebookLM/Slides: Nano Banana Pro (Gemini 3 Pro Image), where exposed.
If the tool exposes a newer Nano Banana-family image model, use the latest available model while preserving the same evidence-bounded prompts.
Current Gemini API image-generation examples use gemini-3.1-flash-image for native image output; do not hard-code an API model inside the deck unless the tool requires it.
```

## Synthetic Scenario Or Evidence Source Pack

This is not a synthetic accuracy demonstration. It is an evidence-governed source packet built from local repo artifacts and generated dashboard screenshots. The scenario is:

1. A non-technical reviewer asks, "What does the database store, and how do ML models improve avalanche prediction?"
2. A scientist asks, "Which lanes are implemented, which are candidate or research-only, and what must be validated before Himalayan claims?"
3. A technical reviewer asks, "Which files and artifacts prove the current implementation map?"
4. The answer must stay bounded by the actual repo and current validation state.

Approved source groups:

| Source group | Examples | Boundary |
|---|---|---|
| Understand Anything graphs | `knowledge-graph.json`, `domain-graph.json`, `fingerprints.json`, `meta.json`, `.understandignore` | Structural evidence only. |
| Deck 6 outputs | HTML, PDF, transcript, QA summary | Teaching/explanation evidence only. |
| Screenshot assets | `ua-structural-overview.png`, `ua-domain-overview.png`, layer screenshots | Durable visual references, not scientific proof. |
| ML implementation files | RF, MTS-LSTM, SAR, Swiss RAvaFcast, Himalayan contract files | Code-grounded lane map. |
| Partner handoff artifacts | CSV templates, field dictionary, source manifest, workorder docs | Evidence intake readiness, not local accuracy proof. |

## Notebook Code Flow And Explanations

### 1. Understand Anything graph metrics

Code/artifact excerpt:

```json
{
  "knowledge_graph": {"nodes": 2045, "edges": 4015, "layers": 10},
  "domain_graph": {"nodes": 50, "edges": 51, "domains": 5, "flows": 10, "steps": 35}
}
```

Explanation: the graph gives reviewers a navigation map through the ML/backend code. It helps locate implemented lanes and claim gates, but it does not measure model skill.

### 2. ML-focused scan boundary

Code/artifact excerpt:

```gitignore
backend/artifacts/
backend/data/swiss_envidat/*
docs/
src/
public/
supabase/
```

Explanation: `.understand-anything/.understandignore` kept the first ML-model graph focused on implemented backend ML, research, and evidence code rather than generated outputs, frontend surfaces, or raw/heavy data.

### 3. Active Random Forest forecast lane

Code/artifact excerpt:

```python
from backend.common.features import FEATURE_COLUMNS
from backend.common.schema_drift import feature_columns_hash, label_schema_hash

PSS_HOLDOUT_ACCEPTANCE_FLOOR = 0.30
DRIFT_FEATURE_MAX_THRESHOLD = 0.18
```

Explanation: the active scorer is a structured Random Forest-oriented pipeline with feature schema controls, calibration reporting, drift checks, and publication guards. It is the current public scoring path, but publishing still depends on gate checks.

### 4. Calibration and probability quality

Code/artifact excerpt:

```python
raw_curve, raw_ece = _build_reliability_bins(labels, raw_probabilities)
calibrated_curve, calibrated_ece = _build_reliability_bins(labels, calibrated_probabilities)
```

Explanation: calibration asks whether model probabilities behave like probabilities. A 70 percent risk output should mean about 7 out of 10 comparable cases over an appropriate validation set, not simply a higher-looking number.

### 5. MTS-LSTM candidate lane

Code/artifact excerpt:

```python
class BranchedMTSLSTM(torch.nn.Module):
    def forward(self, hourly: torch.Tensor, daily: torch.Tensor, static: torch.Tensor) -> torch.Tensor:
        ...
```

Explanation: the MTS-LSTM lane is a candidate sequence model. It can learn temporal stories such as snowfall, wind loading, warming, and settling, but it needs reviewed local sequences and promotion gates before activation.

### 6. SAR shadow lane

Code/artifact excerpt:

```python
def evaluate_snowslide_research_grade(...):
    ...
    "production_scoring_allowed": False
```

Explanation: SAR segmentation can add remote-sensing evidence, but SnowSlide/AvalCD gates and transferability risks keep this lane shadow-only. It is useful research evidence, not a public scorer.

### 7. Swiss RAvaFcast reproduction lane

Code/artifact excerpt:

```python
def compute_refined_discretization_thresholds(
    expected_danger_values: Iterable[float],
    true_labels: Iterable[int],
) -> tuple[float, float, float, float]:
    """Compute RAvaFcast-style thresholds from training/OOB data only."""
```

Explanation: Swiss RAvaFcast work adds methodology discipline: D_tidy label thinking, RF4 reproduction, probability calibration, GPxyz interpolation, and refined aggregation. It does not validate Himalayan performance by itself.

### 8. GPxyz station metadata gate

Code/artifact excerpt:

```python
STATION_METADATA_REQUIRED_COLUMNS = ("station_code", "latitude", "longitude", "elevation_m")
decision = "blocked_station_coordinates_required"
```

Explanation: spatial interpolation requires station X/Y/Z metadata. If coordinates are absent or incomplete, the GPxyz lane fails closed instead of pretending spatial readiness exists.

### 9. Beginner avalanche danger pipeline

Code/artifact excerpt:

```text
Stage 1: classification -> station/cell danger probabilities
Stage 2: spatial interpolation -> GPxyz danger grid plus uncertainty
Stage 3: elevation/region aggregation -> warning-region danger summary
```

Explanation: RAvaFcast-style danger forecasting is easiest to teach as a pipeline rather than a single model score. Stage 1 classifies danger from reviewed weather, snowpack, terrain, and label evidence. Stage 2 interpolates station or cell outputs in space with X/Y/Z metadata and uncertainty. Stage 3 aggregates the spatial field into elevation bands and warning regions. Each stage needs its own data checks, leakage controls, and validation gates.

### 10. Himalayan partner evidence contract

Code/artifact excerpt:

```text
station_metadata.csv
weather_station_observations.csv
snowpack_profile_features.csv
danger_labels_and_bulletins.csv
independent_himalayan_holdout.csv
```

Explanation: Himalayan readiness depends on reviewed partner evidence: station coordinates, weather, snowpack, D_tidy-grade labels, event truth, warning-region geometry, scientist review, and a leakage-checked holdout.

## PPT Creation Source Packet

Deck creation instruction:

Create a 15-slide beginner-friendly technical teaching deck from this Markdown source only. Explain the ML-focused Understand Anything pass as a clear system map: database, active Random Forest scorer, candidate MTS-LSTM, SAR shadow lane, Swiss RAvaFcast research lane, Himalayan evidence contract, and validation/claim gates. Teach avalanche danger prediction as a three-stage pipeline: classification, spatial interpolation, and elevation/region aggregation.

Technical storyline:

1. The website is a governed evidence system, not just a map.
2. The database stores forecast facts, evidence, model state, evaluation records, and reviews.
3. The active ML path is Random Forest plus engineered features, calibration, and publication gates.
4. MTS-LSTM, SAR segmentation, and Swiss RAvaFcast are candidate, shadow, or research lanes with separate gates.
5. European methods improve validation discipline, especially the classification -> interpolation -> aggregation pipeline, but Himalayan claims need local reviewed evidence.
6. The next practical action is partner evidence intake and scientist validation, not unsupported model promotion.

Workflow traceability chain:

`scenario -> approved sources -> data boundary -> code flow -> outputs -> validation -> learner artifact -> slide prompts -> live-transfer gates`

Visual generation and dynamic color system:

| Slide family | Preferred visual model instruction | Dynamic palette guidance |
|---|---|---|
| Database and ledger slides | Use Nano Banana Pro (Gemini 3 Pro Image) in NotebookLM/Slides where available; if the tool exposes a newer Nano Banana-family model, use the latest available image model. | Crisp platinum, luminous azure, daylight cyan, deep graphite. Use color to separate stored facts, review evidence, and publication gates. |
| Classification and RF slides | Same model instruction; keep the image prompt grounded in actual code and evidence paths. | Glacier blue, alpine pine, signal amber, controlled danger red. Use red only for gates or danger thresholds. |
| Spatial interpolation and GPxyz slides | Same model instruction; ask for contours, uncertainty cards, and station X/Y/Z markers. | Topographic teal, elevation cyan, contour gray, sparse uncertainty indigo used sparingly. |
| SAR shadow slides | Same model instruction; do not create dramatic satellite imagery that implies operational activation. | Radar green, ice white, graphite, caution amber. Shadow-gate visuals must be visually obvious. |
| Partner handoff and governance slides | Same model instruction; show human workflow, manifests, checksums, and claim locks. | Clean white, slate, verification green, signal amber. Keep the tone operational, not promotional. |

Visual rules: use high contrast, avoid generic decorative mountain stock art, avoid one-note palettes, use color consistently to encode pipeline stages, and label generated diagrams as explanatory visuals rather than evidence.

Glossary:

| Term | Plain-English meaning |
|---|---|
| Supabase/Postgres | Database ledger for app facts, model state, and review records. |
| Random Forest | Many decision trees voting together from structured features. |
| Classification | Stage 1 of the danger pipeline: estimate danger probabilities from reviewed features and labels. |
| Spatial interpolation | Stage 2 of the danger pipeline: spread station/cell predictions over space while keeping uncertainty visible. |
| Elevation/region aggregation | Stage 3 of the danger pipeline: summarize spatial outputs into elevation bands and warning regions. |
| Calibration | Checking whether probabilities behave like probabilities. |
| TreeSHAP | A method for explaining feature influence in tree models. |
| MTS-LSTM | A candidate sequence model for weather/snowpack time histories. |
| SAR | Satellite radar evidence used in the shadow remote-sensing lane. |
| SnowSlide/AvalCD | SAR evaluation contexts used for remote-sensing qualification. |
| D_tidy | Quality-controlled danger labels, not raw bulletin text alone. |
| GPxyz | Gaussian Process interpolation using latitude, longitude, and elevation. |
| Refined aggregation | Converting expected danger into class outputs with controlled thresholds. |
| Himalayan evidence contract | Partner data schema and gate before Himalayan accuracy claims. |
| Nano Banana Pro | Google/NotebookLM image-generation model family name for Gemini 3 Pro Image visuals where available. |
| Dynamic color system | A slide-design rule that changes colors by function: database, classification, interpolation, SAR, and governance. |

Concrete deck-ready output examples:

Normal request example:

```text
Request: Explain the current ML model stack to a beginner.
Output: ready_for_review deck source with active, candidate, shadow, research, and evidence lanes separated.
```

Ambiguous request example:

```text
Request: Show that the model works for the Himalayas.
Output: needs_clarification. The current source can explain the evidence path, but local Himalayan accuracy needs reviewed data and holdout validation.
```

Unsafe request example:

```text
Request: Say SAR is ready for public avalanche scoring.
Output: blocked refusal. SAR is shadow-gated and must not be described as activated for public scoring.
```

Validation result example:

```text
Deck 6 validation result: 15 slides, 15 PDF pages, viewport QA pass at four screen sizes.
```

Learner artifact excerpt:

```text
Learner artifact: a 15-slide NotebookLM deck source with required fields, code excerpts, callouts, speaker notes, and claim boundaries.
```

Failure or control example:

```text
Missing evidence: if station X/Y/Z, D_tidy labels, or independent holdout rows are absent, Himalayan accuracy claim remains blocked.
```

Slide design rules:

- Use a clean engineering-platform style.
- Use process diagrams, architecture maps, code panels, artifact panels, and evidence boxes.
- Use screenshots only as evidence panels, not decorative backgrounds.
- Keep each slide beginner-readable but scientist-safe.
- Put a claim boundary on every slide.

Presenter explanation notes:

- Translate every technical term into an operational meaning.
- Separate "implemented path" from "candidate path" and "research-only path."
- Emphasize that evidence gates are part of the product strategy.
- Avoid turning local artifacts or European research into Himalayan accuracy claims.

## Expected Lab Outputs

Expected output from NotebookLM:

| Output | Criteria |
|---|---|
| 15-slide deck draft | Exactly 15 slides following the slide prompt pack. |
| Beginner explanation | Database, ML, and evidence gates are understandable without code knowledge. |
| Scientist-safe caveats | D_tidy, local holdout, station coverage, SAR blockers, and claim locks are visible. |
| Technical grounding | Slides cite graph artifacts, Deck 6 outputs, screenshots, and code files. |
| Beginner pipeline | Slides explain classification, spatial interpolation, and elevation/region aggregation as separate stages. |
| Visual model guidance | Image prompts instruct NotebookLM/Slides to use Nano Banana Pro or the latest available Nano Banana-family image model with function-specific color palettes. |
| No overclaim | No unsupported production, SAR, or Himalayan accuracy claim. |

## 15-Slide Deck Prompt Pack For NotebookLM

### Slide 1: Cover - What This Deck Explains

Title: Database, ML Models, And Himalayan Accuracy Path

Teaching goal: Explain that the deck teaches how the database, model lanes, and evidence gates fit together.

Code concepts: Deck 6 transcript, Understand Anything graph artifacts, claim locks.

Code excerpt:

```text
production_scoring_allowed=false
himalayan_accuracy_claim_allowed=false
```

Panel layout: Cover slide with three horizontal blocks: Database, Models, Evidence Gates.

Callouts: "Beginner-friendly", "Scientist-safe", "Repo-grounded", "Claim-bounded".

Image prompt: Create a clean technical diagram with three linked panels labeled database, ML models, and evidence gates.

Speaker notes: Explain that the system is not only a visual map. It stores facts, runs model lanes, and controls which claims may be made.

Claim boundary: Do not imply Himalayan accuracy or SAR public scoring has been proven.

### Slide 2: Artifact Inventory

Title: What Was Generated

Teaching goal: Show which files make the ML-focused Understand Anything pass durable and reviewable.

Code concepts: `knowledge-graph.json`, `domain-graph.json`, `fingerprints.json`, `meta.json`, `.understandignore`, Deck 6 outputs, screenshots, QA.

Code excerpt:

```text
.understand-anything/knowledge-graph.json
.understand-anything/domain-graph.json
docs/MVP_V2/Artifacts/01_deck_pack/avalanche-insight-hub-deck-6-ml-understanding.pdf
```

Panel layout: Artifact table on the left, screenshot strip on the right.

Callouts: "Graph JSON", "Dashboard screenshots", "Deck 6 PDF", "QA summary", "Ignore policy".

Image prompt: Create an artifact inventory board with file cards grouped by graph, deck, screenshots, and validation.

Speaker notes: Explain that NotebookLM should use this Markdown as source, while the listed files are traceability anchors.

Claim boundary: File presence proves documentation and code-structure evidence, not model skill.

### Slide 3: Structural Graph

Title: 2,045 Nodes, 4,015 Edges, 10 Layers

Teaching goal: Help beginners understand what the structural graph means.

Code concepts: `knowledge-graph.json`, structural layers, graph nodes, graph edges.

Code excerpt:

```json
{"nodes": 2045, "edges": 4015, "layers": 10}
```

Panel layout: Main graph screenshot with three metric cards underneath.

Callouts: "Nodes are files/functions", "Edges are relationships", "Layers group workstreams", "Navigation aid".

Image prompt: Use `ua-structural-overview.png` as the main evidence panel and add simple metric cards.

Speaker notes: Explain that the graph helps reviewers find implemented code lanes and gates. It does not calculate accuracy.

Claim boundary: Do not present graph size as evidence of forecast quality.

### Slide 4: Domain Graph

Title: Five Domains, Ten Flows, Thirty-Five Steps

Teaching goal: Show the higher-level workflow map created by the domain graph.

Code concepts: `domain-graph.json`, domain, flow, step.

Code excerpt:

```json
{"domains": 5, "flows": 10, "steps": 35}
```

Panel layout: Domain graph screenshot plus a 5-domain list.

Callouts: "Forecast decision support", "Remote-sensing validation", "Scientific reproduction", "Himalayan readiness", "Release governance".

Image prompt: Use `ua-domain-overview.png` and show a simple hierarchy: domain -> flow -> step.

Speaker notes: Explain that the domain graph is easier for non-engineers than the file-level structural graph.

Claim boundary: Do not imply every domain is equally complete or public-facing.

### Slide 5: Database In Plain English

Title: The Database Is The System Ledger

Teaching goal: Explain what the database stores and why it matters.

Code concepts: forecast runs, grid cells, events, model status, evaluation records, scientist reviews.

Code excerpt:

```text
forecast_runs -> forecast_grids -> public map
avalanche_events -> evaluation_runs -> scientist_validation_reviews
model_status -> publication gates
```

Panel layout: Ledger diagram with three sections: forecast facts, ground evidence, governance.

Callouts: "Forecast facts", "Event evidence", "Model state", "Scientist review", "Daily verification".

Image prompt: Create a database ledger diagram with rows flowing into a public map and review records.

Speaker notes: Explain that the database is the record of what was generated, reviewed, and allowed to publish.

Claim boundary: Do not claim the current UI collects the full Himalayan partner evidence package.

### Slide 6: Forecast Run To Public Map

Title: Inputs Become A Published Grid Only Through Gates

Teaching goal: Show the end-to-end flow from inputs to grid cells to public display and review.

Code concepts: weather, terrain, snowpack proxies, event history, daily inference, grid publication.

Code excerpt:

```text
inputs -> daily_inference.py -> forecast run -> grid cells -> publication gate -> public map -> review
```

Panel layout: Left-to-right workflow strip with a gate icon before the public map.

Callouts: "Inputs", "Forecast run", "Grid cells", "Publication gate", "Review".

Image prompt: Create a workflow strip with technical arrows and a visible gate before publication.

Speaker notes: Explain that prediction output alone is insufficient; lineage, status, freshness, and evidence checks matter.

Claim boundary: Do not claim public display means scientific validation is complete.

### Slide 7: Active RF Avalanche Scorer

Title: Current Public Scoring Path

Teaching goal: Explain why Random Forest is a practical active model lane.

Code concepts: `backend/models/surrogate_rf.py`, `backend/train_model.py`, `backend/daily_inference.py`, feature columns, publication guard.

Code excerpt:

```python
from backend.common.features import FEATURE_COLUMNS
PSS_HOLDOUT_ACCEPTANCE_FLOOR = 0.30
def publish_guard_reason(*, is_synthetic: bool, allow_publish: bool) -> str | None:
    ...
```

Panel layout: Code-left and explanation-right split with a model-lane badge.

Callouts: "Structured features", "Many tree votes", "Calibration reports", "Drift checks", "Publication guard".

Image prompt: Use `ua-active-rf-layer.png` as evidence and add a simple ensemble-tree diagram.

Speaker notes: Explain that Random Forest is useful because it combines many weak patterns instead of relying on one hand-written rule.

Claim boundary: Active scoring does not remove the need for local validation and publication gates.

### Slide 8: Calibration And Explainability

Title: Better Predictions Need Probability Quality

Teaching goal: Explain calibration and explanation controls in plain language.

Code concepts: reliability bins, ECE, Brier score, TreeSHAP-style explanations.

Code excerpt:

```python
raw_curve, raw_ece = _build_reliability_bins(labels, raw_probabilities)
calibrated_curve, calibrated_ece = _build_reliability_bins(labels, calibrated_probabilities)
```

Panel layout: Probability calibration chart on the left, explanation card on the right.

Callouts: "Probability quality", "Expected calibration error", "Feature influence", "Reviewer visibility".

Image prompt: Create a reliability curve plus a small feature-contribution explanation panel.

Speaker notes: Explain that a probability must be checked against outcomes over a valid evaluation set. Explanations help reviewers inspect why risk changed.

Claim boundary: Do not imply explanation tooling proves correctness; it supports review.

### Slide 9: MTS-LSTM Candidate

Title: Sequence Learning For Future Upgrades

Teaching goal: Explain why time-sequence models may help and why they remain gated.

Code concepts: `backend/lstm_model.py`, `backend/models/mts_lstm.py`, hourly branch, daily branch, static branch.

Code excerpt:

```python
class BranchedMTSLSTM(torch.nn.Module):
    self.hourly_lstm = torch.nn.LSTM(...)
    self.daily_lstm = torch.nn.LSTM(...)
```

Panel layout: Three-input sequence diagram feeding a candidate model box.

Callouts: "Hourly history", "Daily history", "Static terrain", "Candidate only", "Needs reviewed sequences".

Image prompt: Use `ua-mts-lstm-layer.png` with a sequence timeline for weather and snowpack.

Speaker notes: Explain that Random Forest sees a structured snapshot, while MTS-LSTM can learn a recent story over time.

Claim boundary: Do not present MTS-LSTM as the current public scorer.

### Slide 10: SAR Shadow Lane

Title: Satellite Evidence, Shadow-Gated

Teaching goal: Explain the value and limits of SAR avalanche segmentation.

Code concepts: `backend/sar_unet_training.py`, `backend/models/swinunet_tiny_diff.py`, `backend/common/sar_acceptance_policy.py`, SnowSlide, AvalCD.

Code excerpt:

```python
def evaluate_snowslide_research_grade(...):
    ...
    "production_scoring_allowed": False
```

Panel layout: Satellite evidence panel plus blocker decision tree.

Callouts: "Sentinel-1 value", "Wet-snow false positives", "Shadow/layover", "Scene transfer", "Held-out gates".

Image prompt: Use `ua-sar-shadow-layer.png` and add a blocked-gate visual labeled shadow lane.

Speaker notes: Explain that SAR can help discover deposits in sparse regions, but transferability and false positives require strict gates.

Claim boundary: SAR must remain outside public scoring in this deck.

### Slide 11: Avalanche Danger Pipeline

Title: Classification To Interpolation To Aggregation

Teaching goal: Teach beginners that avalanche danger prediction is a pipeline, not one isolated model score.

Code concepts: `train_rf4.py`, `interpolate_gpxyz.py`, `aggregate.py`, RF4 classification, GPxyz spatial interpolation, elevation-band aggregation, refined thresholds.

Code excerpt:

```text
classification -> station/cell danger probabilities
GPxyz interpolation -> spatial danger grid + uncertainty
elevation/region aggregation -> warning-region summary
```

Panel layout: Three-stage left-to-right pipeline with a validation gate under each stage and a small Swiss RAvaFcast method card in the corner.

Callouts: "Stage 1 classification", "Stage 2 GPxyz interpolation", "Stage 3 elevation/region aggregation", "Uncertainty stays visible", "Each stage has a gate".

Image prompt: Use `ua-swiss-ravafcast-layer.png` with a three-stage technical pipeline. Generate supporting visuals with Nano Banana Pro (Gemini 3 Pro Image) where NotebookLM/Slides exposes it, or the latest available Nano Banana-family image model. Use glacier blue for classification, topographic teal for interpolation, verification green for aggregation, and signal amber for gates.

Speaker notes: Explain that RAvaFcast-style work improves how the team structures the problem: classify danger, interpolate across space, and aggregate into useful warning-region summaries. This is methodology discipline, not Himalayan proof.

Claim boundary: Do not treat Swiss results, pipeline diagrams, or generated visuals as Himalayan proof.

### Slide 12: Himalayan Evidence Contract

Title: What Himalayas Need Before Claims

Teaching goal: List the local partner evidence required for Himalayan readiness and show which pipeline stage each input supports.

Code concepts: `backend/reproduction/himalayan_accuracy_contract.py`, partner templates, D_tidy labels, station X/Y/Z, independent holdout.

Code excerpt:

```text
station_metadata.csv
weather_station_observations.csv
snowpack_profile_features.csv
danger_labels_and_bulletins.csv
independent_himalayan_holdout.csv
```

Panel layout: Checklist table with owner column, gate status column, and pipeline-stage column.

Callouts: "D_tidy labels feed classification", "Station X/Y/Z feeds interpolation", "Warning polygons feed aggregation", "Weather and snowpack feed model features", "Leakage-checked holdout validates the full chain".

Image prompt: Use `ua-himalayan-evidence-layer.png` and overlay a partner-evidence checklist grouped into classification inputs, interpolation inputs, aggregation inputs, and validation inputs. Use Nano Banana Pro or the latest available Nano Banana-family image model with clean white, slate, verification green, and signal amber.

Speaker notes: Explain that public bulletins are useful context, but quality-controlled local evidence is needed for training and validation.

Claim boundary: Do not claim Himalayan accuracy from templates or synthetic smoke checks.

### Slide 13: Validation Evidence

Title: What Was Verified For The Deck Pack

Teaching goal: Show the difference between deck validation and scientific validation.

Code concepts: `QA_SUMMARY.md`, Deck 6 slide count, PDF pages, viewport QA.

Code excerpt:

```text
Deck 6 - ML Understanding
slide count: 15
pdf pages: 15
viewport QA: pass at 1920x1080, 1280x720, 768x1024, 390x844
```

Panel layout: QA table plus warning strip separating presentation QA from model validation.

Callouts: "15 slides", "15 PDF pages", "Viewport pass", "Screenshots captured", "Scientific gates still separate".

Image prompt: Use `ua-tests-ci-layer.png` with a validation checklist panel.

Speaker notes: Explain that the deck is visually and structurally checked, while scientific acceptance depends on separate data and model gates.

Claim boundary: Do not confuse deck QA with forecast accuracy validation.

### Slide 14: Scientist And Partner Handoff

Title: Who Does What Next

Teaching goal: Make the co-working model concrete for Sanjay team, partners, and scientists.

Code concepts: partner handoff packet, field dictionary, source manifest, CSV templates, scientist reviews.

Code excerpt:

```text
partner_source_manifest_template.json
partner_field_dictionary.md
scientist_reviews.csv
partner_submission_quality_score.md
```

Panel layout: Three-column responsibility table: Sanjay team, partner agency, scientist reviewers.

Callouts: "Prepare handoff", "Fill source manifests", "Review D_tidy labels", "Run triage", "Record gate decisions".

Image prompt: Create a handoff workflow with three swimlanes and artifact cards.

Speaker notes: Explain that the next high-value work is partner evidence intake and scientist adjudication, not changing claim wording.

Claim boundary: Do not imply all scientist actions are currently available through the UI.

### Slide 15: Next Actions And Do-Not-Say Guardrails

Title: The Safe Path Forward

Teaching goal: Close with practical actions and blocked claims.

Code concepts: partner triage, pipeline-stage readiness, release gates, claim locks, blocked phrases.

Code excerpt:

```text
Next: collect reviewed partner evidence -> validate classification/interpolation/aggregation readiness -> run triage -> scientist adjudication -> local holdout -> narrow pilot decision.
```

Panel layout: Roadmap with approval gates and a do-not-say sidebar.

Callouts: "Collect evidence", "Validate each pipeline stage", "Run triage", "Review with scientists", "Holdout validation", "Only then pilot".

Image prompt: Create a gated roadmap from evidence intake to narrow pilot decision, with three embedded stage checks for classification, spatial interpolation, and elevation/region aggregation. Use Nano Banana Pro or the latest available Nano Banana-family image model; keep blocked-claim chips visibly separate from the progress path.

Speaker notes: Explain that the strongest story is evidence discipline: current live technical proof plus a serious path to Himalayan validation.

Claim boundary: Avoid saying Himalayan accuracy is established, SAR is activated for public scoring, or the platform replaces regional forecasters.

## Master Prompt For NotebookLM

Create a 15-slide technical teaching deck from this Markdown source only.

Audience: beginner-friendly for non-technical stakeholders, credible for avalanche scientists, and grounded enough for technical reviewers.

Goal: explain the implemented ML-focused Understand Anything pass for Avalanche Insight Hub MVP V2. Teach the database, active Random Forest scorer, candidate MTS-LSTM, SAR shadow lane, Swiss RAvaFcast research lane, Himalayan partner evidence contract, validation boundaries, and the three-stage avalanche danger pipeline: classification, spatial interpolation, and elevation/region aggregation.

Rules:

- Use exactly 15 slides.
- Preserve every slide's `Claim boundary`.
- Use the code excerpts and artifact paths as grounding material.
- Do not invent model metrics or operational claims.
- Keep `production_scoring_allowed=false` and `himalayan_accuracy_claim_allowed=false` visible.
- Make the difference between structural evidence, deck QA, and scientific model validation explicit.
- Use the screenshot filenames as visual evidence prompts, not as unsupported product claims.
- Keep SAR shadow-gated.
- Keep Swiss/European research as methodology transfer, not Himalayan accuracy proof.
- Teach classification, spatial interpolation, and elevation/region aggregation as separate stages with separate data requirements and gates.
- Use Nano Banana Pro (Gemini 3 Pro Image) for generated visuals where NotebookLM/Slides exposes it. If a newer Nano Banana-family image model is available in the tool, use that latest model while preserving these prompts and claim boundaries.
- Apply a dynamic color system by slide function: database, classification, interpolation, SAR, partner handoff, and governance.
- End with partner evidence intake, scientist adjudication, and local holdout validation as next actions.

Preferred visual style:

- Clean engineering-platform deck.
- Dense but readable diagrams, artifact panels, evidence boxes, code snippets, and gate roadmaps.
- Use subdued technical colors, not decorative marketing visuals.
- Avoid generic mountain stock imagery unless it explains terrain, evidence, or workflow.
- Use function-specific palettes: luminous azure for database, glacier blue for classification, topographic teal for interpolation, verification green for aggregation, radar green for SAR, and signal amber for gates.
