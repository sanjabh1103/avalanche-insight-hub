# Map Input Request

## Status: BLOCKED

No approved, rights-cleared static map snapshot exists in the source repository.

## What Was Searched

The following source locations were searched for static map/forecast artifacts:

- `backend/data/`
- `artifacts/`
- `docs/MVP4/`
- `docs/MVP3/`

## What Was Found

| Path | Status | Reason |
|---|---|---|
| `backend/data/swiss_envidat/data_rf1_forecast.csv` | REJECTED | Contains private station codes (KES2, SIM2, DTR2, etc.). Research dataset from Envidat. Not rights-cleared for public redistribution. 185MB. |
| `backend/data/swiss_envidat/data_rf2_tidy.csv` | REJECTED | Same dataset family. Contains private station identifiers. |

**Approved snapshots found: 0**

## What Is Required

To unblock the map, supply a static forecast snapshot with:

1. **Source name** — organization or system that produced the data
2. **Source URL or citation** — where the data originates
3. **License** — under what terms the data can be redistributed
4. **SPDX identifier** — if available (e.g., CC-BY-4.0, ODbL-1.0)
5. **Attribution text** — exact text to display on the map
6. **Source file hash** — SHA-256 of the source file
7. **Geographic coverage** — bbox or region name
8. **Valid-from time** — ISO-8601 timestamp
9. **Valid-to time** — ISO-8601 timestamp
10. **Uncertainty statement** — known limitations
11. **Public-use approval** — explicit confirmation that public redistribution is approved

## What Must NOT Be Included

- Station locations
- Geophone locations
- Personal reports
- Exact addresses
- Private observation identifiers
- Raw Supabase IDs
- Raw API response payloads
- Unapproved exact coordinates

## Current State

The map UI shows an explicit `MAP_SNAPSHOT_NOT_AVAILABLE` blocked state. No fabricated or synthetic data is used. The graph implementation proceeds independently.

## Next Action

Supply an approved static forecast snapshot to `public/data/forecast-map.json` with the schema defined in `public/data/forecast-map-manifest.json`, then re-run the sanitizer and build.
