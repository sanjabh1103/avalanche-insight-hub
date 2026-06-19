# Avalanche Insight Hub — Database, ML Models, And Himalayan Accuracy Path Transcript

## D6-1 — Database, ML Models, And Himalayan Accuracy Path

_MVP V2 explanation deck_

A beginner-friendly guide to what the Understand Anything graphs show, how the current model stack works, and what evidence is still needed before Himalayan accuracy can be claimed.

Evidence lanes: Technical evidence; Research agenda

Plain-English purpose

This deck explains the system as three connected parts: a database that stores facts, machine-learning models that estimate risk, and evidence gates that decide what may be shown or claimed.

For beginners

No code reading required; every technical term is mapped to a simple operational meaning.

For scientists

The deck keeps label quality, validation data, SAR limits, and local holdout gates visible.

Understand Anything • structural overview

---

## D6-2 — Three Things To Remember

_One-minute mental model_

The website is not just a map. It is a governed evidence system: store facts, run models, then publish only what passes the right gates.

Evidence lanes: Technical evidence

1 · Database

Stores the facts

Supabase/Postgres stores forecast runs, grid cells, events, model status, evaluation records, scientist reviews, and daily verification records.

2 · Models

Estimate risk

Random Forest is the active structured scorer; MTS-LSTM, SAR segmentation, and Swiss RAvaFcast remain gated research or candidate lanes.

3 · Evidence gates

Control claims

Publication, SAR, Himalayan partner, and holdout gates stop unsupported claims even when a model or graph looks promising.

Domain overview

Active RF

Himalayan evidence

---

## D6-3 — What The Graph Is Showing

_Dashboard map_

Understand Anything turned the repo into a visual map: 2,045 nodes, 4,015 edges, and 10 ML/backend layers for the structural view.

Evidence lanes: Technical evidence

10 structural layers

Nodes

2,045

Files, functions, classes, pipelines, config, and docs.

Edges

4,015

Relationships that show how code and evidence connect.

Layers

10

Grouped ML/backend workstreams, not random file lists.

The graph is a navigation aid. It does not prove scientific accuracy by itself; it helps reviewers see where the implemented evidence and remaining gates live.

---

## D6-4 — The Database In Plain English

_Database basics_

The database is the system ledger: it records forecast products, event evidence, model state, evaluation runs, and scientist review decisions.

Evidence lanes: Technical evidence

Forecast facts

Runs and grid cells

`forecast_runs`, `forecast_run_hours`, `forecast_grids`, and publication events record what was generated and published.

Ground evidence

Events and reports

`avalanche_events`, field reports, outcome labels, and feature logs form the evidence trail behind model evaluation.

Governance

Status and reviews

`model_status`, `evaluation_runs`, `scientist_validation_reviews`, and daily verifications keep model state and human checks visible.

Backend support

Governance tables

---

## D6-5 — Forecast Run To Public Map

_Database flow_

A beginner can read the data path as a chain: inputs become a model run, the run writes grid cells, the public map reads the published grid, and scientists review exceptions.

Evidence lanes: Technical evidence

Core flow

Inputs
Weather, terrain, snowpack proxies, event history, and model status.

Forecast run
Backend scoring creates a dated run with lineage and metadata.

Grid cells
Cell-level risk values become the map surface and bulletin context.

Review
Scientists and operators inspect cases, actions, and daily verification records.

What is not UI-complete today

Himalayan partner evidence intake is still CSV, source-manifest, and CLI based. The current UI supports product and review concepts, but the full partner evidence package is not yet a web form workflow.

Review/gates

Data flow support

---

## D6-6 — Current ML Model Map

_Model ladder_

The system deliberately separates active, candidate, shadow, research, and evidence lanes so one promising result does not become an unsupported public claim.

Evidence lanes: Technical evidence; Research agenda

Active RF layer

Five lanes

Active
Random Forest with terrain, weather, and snowpack features.

Candidate
MTS-LSTM for future temporal learning.

Shadow and research
SAR shadow plus Swiss RAvaFcast RF4, GPxyz, and refined aggregation.

Evidence and claim lock
Himalayan partner evidence; `production_scoring_allowed=false`; `himalayan_accuracy_claim_allowed=false`.

---

## D6-7 — How Random Forest Improves Prediction

_Active model_

Random Forest is a practical baseline: it combines many simple decision trees so the final estimate is less fragile than one hand-written rule.

Evidence lanes: Technical evidence

Input features

More than one signal

Terrain, weather, snowpack proxies, historical context, and freshness cues become structured columns for the model.

Tree ensemble

Many small votes

Each tree learns a different split pattern; the ensemble combines them to reduce dependence on a single brittle rule.

Publication gate

Prediction is not enough

The score must still pass model-status, lineage, freshness, and confidence controls before it is safe to publish.

RF layer

Publication gates

---

## D6-8 — Calibration And Explainability

_Quality controls_

Good prediction is not only the top class. The system also needs probability quality, explanation traces, and publication proof.

Evidence lanes: Technical evidence

Calibration

Calibration checks whether a probability behaves like a probability. If the model says 70% risk often, roughly 7 out of 10 comparable cases should behave that way over a valid evaluation set.

Explainability

TreeSHAP-style explanations and feature summaries help reviewers see why a cell moved up or down, instead of treating the model as a black box.

The current deck keeps explanation and calibration as evidence controls, not as magic. If a run falls back to heuristic explanation, that must remain visible.

Evaluation layer

Test gates

---

## D6-9 — Why MTS-LSTM May Help Later

_Candidate model_

Avalanche danger changes over time. A sequence model can learn recent weather and snowpack progression, but it needs enough reviewed local sequences before promotion can be discussed.

Evidence lanes: Research agenda

Beginner version

Random Forest sees a structured snapshot. MTS-LSTM can learn a short story over time: wind loading, snowfall, warming, settling, and changing instability.

Potential benefit

Better use of multi-day weather and snowpack sequences.

Current boundary

Candidate lane only; it needs reviewed data, benchmark gates, and drift checks before activation.

MTS-LSTM layer

Candidate gates

---

## D6-10 — SAR Shadow Lane

_Remote sensing_

Satellite radar can reveal avalanche deposits in places with sparse ground reports, but this lane remains shadow-gated because transferability and false positives are real scientific risks.

Evidence lanes: Technical evidence; Research agenda

SAR shadow lane

Why it helps
Sentinel-1 can monitor large remote areas through cloud cover.

Why it is gated
Wet snow, crevasses, shadow/layover, small events, and scene transfer can distort detections.

Current posture
AvalCD and SnowSlide evidence are valuable, but SAR stays out of public scoring until held-out gates pass.

---

## D6-11 — What Europe Adds To The Method

_European evidence_

European datasets and papers improve the methodology: label discipline, common danger language, spatial interpolation, aggregation, and remote-sensing caution.

Evidence lanes: Technical evidence; Research agenda

Swiss RAvaFcast research lane

European method lessons

EAWS scale
Shared 1-5 danger language.

NHESS 2022
`D_tidy` labels and Random Forest baseline discipline.

GMD 2024
Swiss RAvaFcast RF, GPxyz, and refined aggregation.

The Cryosphere 2024
SAR transfer limits, wet-snow false positives, small misses, shadow/layover.

AvalCD
SAR change-detection benchmark context.

Claim discipline
Method transfer only; Himalayan proof needs local reviewed data.

---

## D6-12 — Why This Helps Himalayas, But Is Not Enough

_Himalayan transfer_

The European work gives a strong blueprint. Himalayan readiness still needs local reviewed labels, station coverage, event truth, warning-region geometry, and an independent holdout.

Evidence lanes: Research agenda

Himalayan partner evidence

Critical boundary

Swiss and European evidence can improve the playbook, feature discipline, and validation gates. It cannot substitute for Himalayan station X/Y/Z metadata, D_tidy-grade local labels, event evidence, polygons, and a leakage-checked holdout.

---

## D6-13 — Himalayan Data Checklist

_Partner checklist_

This is the practical input list partners and scientists must fill before local claims can advance.

Evidence lanes: Research agenda

Core files to fill

Station X/Y/Z
`station_metadata.csv`

Weather
`weather_station_observations.csv`

Snowpack
`snowpack_profile_features.csv`

D_tidy labels
`danger_labels_and_bulletins.csv`

Events and terrain
`historical_avalanche_events.csv`, `terrain_ates_runout_validation.csv`

Regions and holdout
`warning_region_polygons.csv`, `independent_himalayan_holdout.csv`

Fields that matter most

- `source_ref`, `license_scope`, `review_status`, `reviewer_id`, and `reviewed_at`.

- Latitude, longitude, elevation, validity windows, avalanche regime, label source, and reviewer notes.

Partner contract

Evidence domains

---

## D6-14 — Beginner FAQ

_Technology FAQ_

The technology stack is easier to understand when each tool is tied to a simple job.

Evidence lanes: Technical evidence

React + Vite
Builds the website screens and packages the frontend quickly.

Supabase + PostGIS
Stores database tables, auth, storage, functions, and geospatial map facts.

Python + scikit-learn
Runs data preparation, Random Forest, calibration, evaluation, and reports.

PyTorch
Supports MTS-LSTM candidate models and SAR segmentation experiments.

Modal
Runs bounded heavier compute jobs outside the public click path when authorized.

Understand Anything
Creates visual codebase maps so reviewers can see how the system fits together.

Code map

Remote compute

Backend

---

## D6-15 — What To Do Next, And What Not To Say

_Next actions_

The path forward is practical: collect local evidence, run triage, validate with scientists, then decide whether a narrow Himalayan pilot is justified.

Evidence lanes: Technical evidence; Research agenda

Next actions

- Send partner handoff packet and ask for reviewed Himalayan source packages.

- Run partner package triage and source-manifest validation.

- Have scientists adjudicate label quality, station coverage, event truth, and holdout validity.

- Advance only a narrow pilot if local gates pass.

Avoid saying:
Himalayan accuracy is established, SAR is activated for public scoring, or the platform replaces regional avalanche forecasters.

Allowed current framing

Evidence-governed MVP V2 with a live technical proof region, active Random Forest baseline, research-only Swiss and SAR lanes, and a Himalayan partner evidence path.

Next evidence path

Release gates
