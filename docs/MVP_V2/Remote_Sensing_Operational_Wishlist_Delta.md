# Remote Sensing Operational Wishlist Delta

Status date: 2026-05-22

Source: customer scanned wishlist, `Adobe Scan 22 May 2026.pdf`.

## Decision

The wishlist expands the product vision, but it does not replace the current
Swiss RAvaFcast reproduction plan. The correct implementation posture is:

- continue Swiss RAvaFcast reproduction inside this repo;
- keep SAR and broader remote-sensing work shadow-gated;
- do not claim full operational avalanche or landslide detection until separate
  validation datasets and release gates exist;
- treat landslide detection as a sibling future lane, not as an automatic
  extension of the avalanche danger-rating pipeline.

## What The Wishlist Adds

| Wishlist Area | Meaning For This Project | Current Coverage | Gap Rating /5 | Action |
|---|---|---|---:|---|
| Multi-source satellite data | Sentinel-1 SAR, Sentinel-2/Landsat optical, and possible commercial imagery | SAR lane exists; optical/commercial lane is not operational | 4 | Add modality-specific adapters behind shadow gates |
| Preprocessing | Radiometric correction, cloud masking, atmospheric correction, orthorectification, co-registration | Partial SAR handling and DEM use | 4 | Document preprocessing contracts before more training |
| InSAR / coherence / deformation | Use deformation and coherence maps as features | Mostly absent | 5 | Run feasibility spike with data availability and cost review |
| DEM integration | Terrain context for displacement and hazard maps | DEM/terrain features already exist in app | 3 | Extend feature-stack manifest for remote-sensing products |
| Feature fusion | Combine optical, SAR, DEM, weather, sensors, reports | Partial across separate lanes | 5 | Add a multimodal feature-stack spec |
| ML/DL detection | U-Net/CNN segmentation plus RF/SVM baselines | SAR U-Net exists as shadow evidence; landslide absent | 4 | Keep task-specific model registries and gates |
| Post-processing | Morphology/artifact removal and validation | SAR post-processing exists | 3 | Add modality-specific postprocess policy |
| Detection maps | Avalanche/landslide map products | Avalanche forecast map exists; event detection maps are not production | 5 | Add as future shadow product, not public claim |
| Alert system | Automated alert dissemination to agencies/operators | Forecast UI exists; alert workflow not operational | 4 | Define alert policy only after validation gates |
| Feedback loop | Field observations and retraining | Scientist review workflow exists | 3 | Reuse scientist validation with remote-sensing evidence types |

## Detection Maps Are Not The Same As Danger Ratings

| Track | Question Answered | Current Evidence | Release Boundary |
|---|---|---|---|
| Swiss RAvaFcast reproduction | Can we reproduce a 4-class danger-level workflow from station weather/snowpack labels? | Stage-1 RF4 and station-row aggregation artifacts exist | Research-only |
| SAR avalanche segmentation | Can we detect avalanche deposits/extent from SAR masks? | AvalCD/SnowSlide shadow artifacts exist, but SnowSlide gates remain strict | Shadow-only until accepted research-grade and fresh-final holdout |
| Optical / InSAR detection | Can optical and deformation features improve event detection? | Wishlist only; no operational lane | Future research spike |
| Landslide detection | Can the same architecture identify landslides? | Not validated in this repo | Separate dataset, labels, metrics, and product gate required |

## Required Validation Before Any Operational Claim

| Claim | Minimum Evidence Required | Current State |
|---|---|---|
| Avalanche danger-rating parity | Station metadata, GPxyz run, official warning-region polygons, region/day metrics | Blocked on station lat/lon and polygons |
| Avalanche remote-sensing detection | Independent labeled SAR/optical scenes, component/IoU/F1/FPR gates, fresh holdout | Shadow-gated |
| Landslide detection | Landslide-specific imagery, labels, event inventory, terrain validation, release floors | Not started |
| Automated alerts | Detection/danger model validation plus false-alarm policy and human approval workflow | Not authorized |
| Commercial imagery use | License, budget, redistribution rights, source-specific data contract | Pending |

## Implementation Backlog

| Priority | Item | Output |
|---:|---|---|
| 1 | Multimodal feature-stack manifest | Source, preprocessing, feature, label, and gate schema for SAR/optical/DEM/weather/report fusion |
| 2 | SAR/optical preprocessing contract | Required corrections, masks, co-registration, and artifact-removal policy |
| 3 | InSAR feasibility spike | Data source, compute cost, coherence/deformation feature viability |
| 4 | Detection-map validation protocol | Metrics for component-level detection, IoU, F1, FPR, and false-alarm burden |
| 5 | Alert workflow design | Human-in-the-loop alert policy, severity thresholds, and audit log |
| 6 | Landslide lane scoping | Separate datasets, task definition, and acceptance gates |

## Do Not Say

- Do not say the product already performs operational landslide detection.
- Do not say Swiss RAvaFcast reproduction proves Himalayan avalanche accuracy.
- Do not say SAR/optical/InSAR fusion is production-ready.
- Do not say automated alerts are active for disaster management.
- Do not use commercial imagery names as available inputs until license and API
  access are reviewed.

## Current Plan Impact

The customer wishlist adds a product-scope backlog. It does not change the next
Swiss reproduction blocker: station latitude/longitude metadata is still
required before full GPxyz interpolation can run.
