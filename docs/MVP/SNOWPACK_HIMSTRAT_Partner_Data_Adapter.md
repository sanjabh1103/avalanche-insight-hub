# SNOWPACK / HIM-STRAT Partner Data Adapter

Version: 1.1

## Purpose

Define the minimum partner-data contract needed before Avalanche Insight Hub can move beyond seasonal snowpack proxies toward SNOWPACK / HIM-STRAT-class validation. The adapter accepts station-level snowpack and weather inputs and translates them into validation evidence. It does not promote production scoring or operational warning authority.

## Required Partner Fields

| Field | Required | Type / units | Notes |
|---|---:|---|---|
| `station_id` or `site_id` | yes | string | Stable partner identifier; must not collide with internal IDs. |
| `region_key` | yes | string | Must not use synthetic or demo region keys. |
| `observed_at` | yes | ISO 8601 | Date or timestamp with timezone. |
| `latitude` | yes | decimal degrees | WGS84. |
| `longitude` | yes | decimal degrees | WGS84. |
| `elevation_m` | yes | meters | Above mean sea level. |
| `layer_index` | preferred | integer | 1 = surface layer, increasing downward. |
| `layer_depth_cm` | preferred | centimeters | Required for weak-layer validation. |
| `grain_type` | preferred | ICSSG-2009 short code | Examples: `PP`, `DF`, `RG`, `FC`, `DH`, `SH`, `MF`, `IF`. |
| `hardness_index` | preferred | 1-6 ordinal | 1=fist, 2=four-finger, 3=one-finger, 4=pencil, 5=knife, 6=ice. |
| `temperature_c` | preferred | Celsius | Snow layer temperature. |
| `density_kg_m3` | optional | kg/m3 | Useful for runout and slab characterization when available. |
| `stability_index` | preferred | partner-defined float | HIM-STRAT / SNOWPACK / field-test comparison target. |
| `quality_flag` | yes | enum | `verified`, `provisional`, or `rejected`. |
| `license_scope` | yes | enum | `training_eligible`, `benchmark_only`, `research_only`, or `demo_only`. |
| `provenance` | yes | JSON object | Include source, observer_role, capture_method, and processing notes. |

## File Formats Accepted

- CSV, UTF-8, header row required.
- Parquet, preferred for larger station feeds.
- JSON Lines, one record per line.

Large payloads should be chunked by station and month. Every delivery should include a manifest with row counts, date range, coordinate reference system, license scope, and contact person.

## Validation Rules

- `latitude` must be between -90 and 90.
- `longitude` must be between -180 and 180.
- `elevation_m` must be between 0 and 9000.
- `layer_depth_cm` must be between 0 and 1500.
- `temperature_c` must be between -50 and 5.
- Rows with `quality_flag = rejected` are loaded only for audit and excluded from validation metrics.
- Rows missing required fields are quarantined and must not generate training or public-scoring signals.
- Rows with `region_key` beginning with `demo_` are rejected by the adapter.

## Adapter Rules

- Current `snowpack_proxy.py` remains a seasonal cumulative proxy, not full SNOWPACK.
- Partner rows must carry provenance and license scope before benchmark use.
- Missing or provisional rows may create `evidence_request` actions.
- Synthetic demo rows are forbidden in this adapter.
- Partner data can support validation cases only after provenance and license checks pass.

## Mapping To Internal Features

| Partner field | Internal feature | Use |
|---|---|---|
| `layer_depth_cm` + `grain_type` | `weak_layer_signature` | Weak-layer validation cases. |
| `stability_index` | `snowpack_stability_observed` | Comparison against snowpack proxy evidence. |
| `hardness_index` | `snow_hardness_band` | HIM-STRAT-style layer interpretation. |
| `density_kg_m3` | `density_observed` | Optional slab/runout calibration evidence. |
| `quality_flag` | `source_quality_status` | Controls quarantine and evidence weighting. |
| `license_scope` | `usage_boundary` | Blocks unintended training or publication use. |

## Quarantine And Failure Modes

| Failure | Detection | Action |
|---|---|---|
| Missing required field | adapter validator | Row quarantined; evidence request opened. |
| Out-of-range value | range check | Row quarantined. |
| Duplicate station/time row | unique key | Latest row wins; prior version archived. |
| License conflict | `license_scope` audit | Row refused until resolved. |
| Demo region key | `region_key` prefix check | Row rejected. |

## Round-Trip Reporting

Partners receive a monthly report with:

- accepted row count
- quarantined row count and reasons
- evidence requests opened from partner rows
- validation cases linked to partner data
- license-scope summary
- unresolved schema or data-quality issues

## Reference Standards

- ICSSG-2009 grain-type codes.
- IACS snow hardness scale.
- HIM-STRAT methodology represented in `docs/publications/2020 _ 10.1007_s11069-020-04032-6 _ HIM-STRAT.pdf`.
- EAWS avalanche problem terminology for review outputs.
