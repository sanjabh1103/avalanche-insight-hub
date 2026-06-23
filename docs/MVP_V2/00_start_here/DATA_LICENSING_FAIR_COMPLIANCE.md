# Data Licensing & FAIR Compliance Posture

Status: 2026-06-24
Purpose: Document the licensing terms of all data sources used by the Avalanche Insight Hub, and the platform's alignment with FAIR (Findable, Accessible, Interoperable, Reusable) principles.
Boundary: This document is for scientist review and compliance audit. No data source is used beyond its license scope.

---

## 1. Data Source Licensing Matrix

| Data Source | License | Commercial Use | Attribution Required | Usage in Platform | License Verification |
|---|---|---|---|---|---|
| **Open-Meteo Global Weather API** | CC-BY 4.0 | Yes | Yes (Open-Meteo) | Weather features: temperature, precipitation, wind, radiation, snowfall | https://open-meteo.com/en/docs |
| **Sentinel-1 SAR (Copernicus)** | Copernicus Open License | Yes (free for research & commercial) | Yes (Copernicus) | SAR backscatter for avalanche detection research (shadow-gated) | https://scihub.copernicus.eu/twiki/pub/SciHubWebPortal/TermsConditions/TC_Copernicus.pdf |
| **SRTM DEM (NASA)** | NASA Open Data (public domain) | Yes | No (public domain) | Elevation downscaling, terrain features, slope/aspect computation | https://www2.jpl.nasa.gov/srtm/ |
| **EnviDat (WSL/SLF Switzerland)** | WSL Terms of Use | Research only | Yes (WSL/SLF) | Swiss RAvaFcast reproduction (research-only lane) | https://www.wsl.ch/en/about-wsl/open-data-and-open-platforms/ |
| **OpenStreetMap (OSM)** | Open Database License (ODbL) | Yes | Yes (OSM) | Infrastructure/road proximity features, 3D voxel neighborhood rendering | https://www.openstreetmap.org/copyright |
| **Gemini LLM (Google AI)** | Google Generative AI API Terms | Yes (API terms) | No | News scraping for avalanche event detection (groundsource enrichment) | https://ai.google.dev/terms |
| **NASA FIRMS (Fire Information)** | NASA Open Data | Yes | No | Not currently used (planned for multi-hazard extension) | https://firms.modaps.eosdis.nasa.gov/ |
| **ASF (Alaska Satellite Facility)** | NASA Open Data | Yes | No | Sentinel-1 metadata search (no download without NASA Earthdata login) | https://asf.alaska.edu/data-products/ |

---

## 2. FAIR Principles Alignment

### Findable

| Principle | Platform Implementation | Evidence |
|---|---|---|
| F1: Persistent identifiers | Each forecast run has a unique `forecast_run_id` (UUID). Each artifact batch has a SHA-256 digest. | `supabase/migrations/` — `forecast_active_runs` table with UUID PK |
| F2: Rich metadata | Forecast metadata includes region, hazard type, model version, feature count, PSS, Brier score, calibration method | `backend/common/forecast_publication.py:51-70` |
| F3: Metadata includes identifier | Manifest files link artifact paths to run IDs and digests | `backend/daily_inference.py` — manifest generation |
| F4: Indexed in searchable resource | Public forecast data accessible via Supabase REST API with filtering by region, date, hazard type | Supabase REST endpoints |

### Accessible

| Principle | Platform Implementation | Evidence |
|---|---|---|
| A1: Retrievable by identifier | Forecast runs retrievable by `forecast_run_id` via REST API | `src/hooks/useForecastState.ts` — forecast hydration |
| A2: Open, free protocol | HTTP/HTTPS REST API; no proprietary protocol | Supabase REST |
| A3: Authentication where necessary | Public forecast data: anon key. Scientist data: scientist role JWT. Admin data: admin role JWT. | `supabase/config.toml` — JWT verification settings |
| A4: Metadata accessible even if data unavailable | Forecast metadata persisted separately from grid artifacts; stale forecasts still show metadata | `src/components/DataLatencyBanner.tsx` — shows metadata + stale warning |

### Interoperable

| Principle | Platform Implementation | Evidence |
|---|---|---|
| I1: Common language | JSON for all API responses; GeoJSON-compatible geometry in cells | `backend/daily_inference.py` — JSON output |
| I2: Standard vocabularies | EAWS danger scale (1-5), WMO IBFWS framing, EAWS avalanche problem types | `src/lib/avalancheCopyI18n.ts` — EAWS labels |
| I3: Qualified references | Feature provenance tracked: source model, source scene IDs, governance version | `backend/common/training_dataset.py:150` — `source_model`, `source_scene_ids` |

### Reusable

| Principle | Platform Implementation | Evidence |
|---|---|---|
| R1: Clear license | Each data source has documented license (see Section 1) | This document |
| R2: Detailed provenance | Partner evidence contract enforces source traceability and license scope before training use | `backend/scripts/build_himalayan_accuracy_readiness_contract.py` |
| R3: Community standards | EAWS Matrix 2025, WMO IBFWS, RAvaFcast reproduction methodology | `docs/MVP/source/Reserches.md` — research anchors |
| R4: Usage rights documented | Claim boundary matrix documents what can and cannot be claimed from each data source | `docs/MVP_V2/customer_alignment_gap_report.md` — claim boundary matrix |

---

## 3. Partner Data Handling

### Partner Evidence Contract

All partner-provided data must pass through the partner evidence contract before any training or claim use:

| Requirement | Enforcement | Evidence |
|---|---|---|
| Reviewed license scope | Contract field `license_scope_reviewed` must be `true` | `backend/scripts/build_himalayan_accuracy_readiness_contract.py` |
| Source traceability | Each event record includes `source`, `fusion_source`, `governance_version` | `backend/common/training_dataset.py:150` |
| Provenance metadata | `governed_at` timestamp and `governance_version` on every label | `backend/common/training_dataset.py:332-333` |
| No training without license review | `training_eligible` flag set to `false` if license scope not reviewed | `backend/common/training_dataset.py:152` |

### Partner Data Categories

| Category | Source | Handling | Storage |
|---|---|---|---|
| Station metadata (lat/lon/elevation) | DRDO/DGRE | RLS-protected; scientist/admin access only | Supabase `station_metadata` table |
| Historical avalanche events | DRDO/DGRE | Governed by evidence contract; license scope required | Supabase `avalanche_events_decayed` table |
| Snowpit profiles | DRDO scientists | Uploaded via scientist workbench; review evidence only | Supabase Storage + scientist validation tables |
| Warning-region polygons | DRDO/IMD | Used for aggregation; not for training | Supabase spatial tables |
| Field reports | Scientist field observations | PWA offline submission; queued and synced | Supabase `field_reports` table |

---

## 4. Swiss Reproduction Lane Data Handling

| Data Source | License | Handling | Boundary |
|---|---|---|---|
| EnviDat RF1/RF2 station data | WSL Terms of Use | Downloaded CSVs stored in `backend/data/swiss_envidat/` | `usage_boundary=research_only` on all artifacts |
| EnviDat station metadata | WSL Terms of Use | Station IDs and elevation only; **no lat/lon available** | GPxyz interpolation blocked until lat/lon provided |
| Swiss warning regions | WSL/SLF | Not currently downloaded | Needed for full RAvaFcast Stage 3 parity |

**Key boundary:** All Swiss reproduction artifacts carry `production_scoring_allowed=false`. No Himalayan operational claim is made from Swiss-trained artifacts.

---

## 5. Synthetic Data Policy

| Use Case | Allowed? | Boundary |
|---|---|---|
| Pipeline testing and CI/CD | Yes | Synthetic data only; never mixed with real events in production |
| Demo artifacts (Colorado proof) | Yes | Clearly labeled as synthetic; `is_synthetic=true` in metadata |
| Model training | No (production) | Synthetic data may be used for pipeline validation only, not for production model training |
| Operational accuracy claims | No | No accuracy claim may cite synthetic data as evidence |
| Scientist demo | Yes (with disclosure) | Must explicitly state "synthetic data for pipeline demonstration only" |

**Evidence:** `backend/scripts/generate_synthetic_snowslide.py` — synthetic data generator with `is_synthetic` flag

---

## 6. Attribution Requirements

When presenting or publishing results derived from this platform, the following attributions are required:

| Data Source | Required Attribution |
|---|---|
| Open-Meteo | "Weather data provided by Open-Meteo (https://open-meteo.com)" |
| Sentinel-1 / Copernicus | "Contains modified Copernicus Sentinel data [year]" |
| SRTM | "SRTM data courtesy of NASA/JPL" |
| EnviDat / WSL / SLF | "Data from WSL Institute for Snow and Avalanche Research SLF (https://www.envidat.ch)" |
| OpenStreetMap | "© OpenStreetMap contributors" |
| RAvaFcast methodology | "Methodology based on Pérez-Guillén et al. (2024), GMD 17, 7569–7584" |

---

## 7. Compliance Gaps & Remediation

| Gap | Status | Remediation Plan |
|---|---|---|
| No automated license-scope check on data ingestion | Open | Add license-scope validation to `ingest-event` edge function (Phase 2) |
| Swiss station lat/lon not available | Blocked | Request from WSL/SLF partner or EnviDat data portal |
| No data retention policy for scientist review notes | Open | Define retention period in SLA update (Phase 5) |
| No automated attribution generation in exports | Open | Add attribution footer to CSV/JSON exports (Phase 2) |
