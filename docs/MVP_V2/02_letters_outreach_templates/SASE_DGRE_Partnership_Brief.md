# SASE / DGRE Partnership Brief

Version: 1.1

Reply-by: `<insert date, normally 14 calendar days after sending>`

## Addressees

- Director, Snow and Avalanche Study Establishment (SASE), Manali / Chandigarh
- Director, Defence Geoinformatics Research Establishment (DGRE), Chamoli
- Cc: `<principal investigator / advisory contact>`
- Sender: `<Avalanche Insight Hub operating contact>`

## Purpose

Avalanche Insight Hub seeks partner-verified Himalayan evidence to move from a decision-support prototype to credible regional validation. The request is aligned with the HIM-STRAT lineage represented in `docs/publications/2020 _ 10.1007_s11069-020-04032-6 _ HIM-STRAT.pdf`.

This is a validation and research request. It does not claim operational warning authority, and it does not change public model claims without separate written approval.

## Pilot Region

We propose one pilot region so the first collaboration is reviewable and bounded.

| Rank | Candidate region | Why it is useful |
|---:|---|---|
| 1 | Western Himalaya - Pir Panjal / Greater Himalaya, including Manali, Lahaul, and Spiti | Strong fit for SASE/DGRE experience, weather-station relevance, and published Western Himalaya avalanche inventories. |
| 2 | Garhwal Himalaya - Chamoli, Joshimath, Auli, Mana | Strong case-study lineage and high public-safety relevance. |
| 3 | Sikkim / Kangchenjunga buffer | Useful later if partner data and field reports exist. |

## Data Request

| Data type | Minimum useful shape | Example fields | Why it matters |
|---|---|---|---|
| Historical avalanche events | 50-200 rows for one winter season or one well-documented basin | date, time, latitude, longitude, elevation_m, aspect, avalanche_problem, observed_outcome, confidence, source | Outcome matching and false-positive / false-negative review. |
| HIM-STRAT-style snowpack parameters | Station or region profile by day | station_id, date, layer_index, layer_depth_cm, grain_type, hardness_index, stability_index, quality_flag | Weak-layer and snowpack-memory validation. |
| Weather station feeds | Hourly or daily station observations | station_id, lat/lon, elevation_m, air_temp_c, snow_depth_cm, wind_dir_deg, wind_speed_ms, precipitation_mm | Forecast-feature verification and model comparison. |
| Field reports | 20-100 records for the pilot season | observation_date, location, problem_type, terrain_context, notes, observer_role | Grounded scientist validation cases. |
| Bulletin archive | Daily regional records | region, daypart, danger_level, avalanche_problem, validity_period, forecaster_notes | Paired model-vs-forecaster comparison. |

## Delivery Format

- CSV with UTF-8 header row, Parquet, or JSON Lines.
- Time fields should use ISO 8601 with timezone or explicit local timezone.
- Each row should include provenance and a `quality_flag`.
- Synthetic, provisional, or training-ineligible rows should be marked explicitly.
- If the partner prefers a secure channel, SFTP or a documented REST endpoint is acceptable.

## Proposed Pilot

- Duration: 8 weeks.
- Initial queue: 20-30 candidate cases for scientist confirmation.
- Review target: 5 cases per scientist per week.
- Priority-5 cases: two independent reviews before sign-off.
- Daily paired verification: one region-day per weekday when conditions and records exist.
- Output: sign-off packet, action ledger, paired-verification export, and gap report.

## What The Partner Receives

- Read-only scientist access to the validation workbench and daily-verification page.
- Monthly evidence digest: cases reviewed, actions opened, claim-boundary changes, and model-vs-scientist agreement.
- A returned data-quality report covering missing fields, quarantine reasons, and open evidence requests.
- Right of first review before any public benchmark paper or Zenodo / OSF release derived from partner data.

## Governance Boundary

Partner data will be used for validation and research unless a separate operational agreement is signed. No public claim upgrade, SAR promotion, MTS-LSTM activation, production scoring change, or operational warning posture follows from the data alone.

## License And Attribution

We default to open benchmark outputs only when partner terms permit it. Partner rows can be marked as `training_eligible`, `benchmark_only`, `research_only`, or `demo_only`. Attribution and publication wording will follow the written partner agreement.

## Decisions Needed From Partner

- Pilot region selection.
- Dataset availability and delivery channel.
- Named scientific reviewer or reviewer group.
- Review cadence and escalation path.
- Confidentiality, license, and publication terms.
- Whether outputs may be cited in a public benchmark pack.

## Reply Channel

- Email: `<ops contact>`
- Phone: `<ops contact>`
- Reply-by: `<insert date>`
