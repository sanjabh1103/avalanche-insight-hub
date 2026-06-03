# Himalayan Partner Submission Manifest Diff

Decision: `blocked_manifest_diff_current_package_incomplete`

This manifest compares package file presence, hashes, sizes, row counts, and schema versions across submissions. It does not validate evidence content or authorize claims.

| Gate | Value |
|---|---:|
| Production scoring allowed | `false` |
| Himalayan accuracy claim allowed | `false` |
| Previous snapshot available | `false` |
| Current package complete | `false` |
| Present files | 10 / 11 |
| Missing files | 1 |
| Changed files | 0 |
| Added files | 0 |
| Removed files | 0 |

## Current Files

| Path | Present | Size bytes | Rows | SHA-256 |
|---|---:|---:|---:|---|
| `partner_source_manifest.json` | `false` | 0 | 0 | `missing` |
| `station_metadata.csv` | `true` | 150 | 0 | `20914754dcc91a2f6f30d08e53b549718815dee1c4049cbd6afdd60d406a3dd4` |
| `weather_station_observations.csv` | `true` | 183 | 0 | `a6495f14f774d55cc7d5b3aca2e9af648d8e7c54b9e0349c0023b8f24f91d746` |
| `snowpack_profile_features.csv` | `true` | 184 | 0 | `c36606a15273cfed4b47499bcec60a5cfe159366f3ce2a2b45cf675cbd7c61aa` |
| `danger_labels_and_bulletins.csv` | `true` | 237 | 0 | `e822e4ca44d15187d1261301e0a5f5d56de27ee5dd4ee5a718cd0085c3deb7c6` |
| `warning_region_polygons.csv` | `true` | 144 | 0 | `fdcf7b31e64a9ffe5394162fe33b8f795b34db3e1532909e70aa18edaf915899` |
| `historical_avalanche_events.csv` | `true` | 191 | 0 | `0ef74679bd25eeeb5618d6eb50c64098f8ac6518e5dc1ec1db3ab2f402c00c06` |
| `remote_sensing_validation_scenes.csv` | `true` | 165 | 0 | `d0bfd93aa4e34571d3627a9806233476c65fa6f86ab6f3f0b9bf572ecad680ec` |
| `terrain_ates_runout_validation.csv` | `true` | 159 | 0 | `6029712e843142fe06caeae19e18e6f694912757080babdb3d14f65f4b2de240` |
| `scientist_reviews.csv` | `true` | 147 | 0 | `bc122899e97895fc71c0dd3a86f2de11789444b897a57099669dcaa75d24309b` |
| `independent_himalayan_holdout.csv` | `true` | 156 | 0 | `ddff7fa3eaacb0bd2f83c014f73e6f31024dec136a338972489c3a69070e13e3` |

## Changes

### Added files
- None

### Removed files
- None

### Changed files
- None

### Unchanged files
- None

## Row Count Changes

- None

## Next Actions

- Supply all missing required package files before scientist review.

## Claim Boundary

- Production scoring allowed: `false`
- Himalayan accuracy claim allowed: `false`
- Reason: The manifest diff tracks package file changes only. It is not evidence validation, model accuracy, or production authorization.
