# Sanitization Report

**Scanned at:** 2026-08-04T07:19:27.531392+00:00
**Files scanned:** 23
**Findings:** 0
**Public release status:** `pass`

## Directories Scanned

- `/Users/sanjayb/avalanche-insight-hub-public-knowledge-site/dist`
- `/Users/sanjayb/avalanche-insight-hub-public-knowledge-site/public`

## Findings

No findings. All checks passed.

## Output Hashes

- `forecast-map.json`: `1d53f0b3029fa5c7...`
- `code-graph-manifest.json`: `75b0751410c4ae6f...`
- `source-ledger.json`: `c91b81bf6747e998...`
- `forecast-map-manifest.json`: `75813686c5aca407...`
- `code-graph.json`: `df77d44e305e0877...`
- `explanations.json`: `2c51c71c81e1cb09...`

## Patterns Checked

### Forbidden Strings

- `/Users/`
- `/home/`
- `/root/`
- `C:\`
- `.env`
- `BEGIN PRIVATE KEY`
- `password`
- `secret`
- `token`
- `api_key`
- `apikey`
- `sk-`
- `ghp_`
- `github_pat_`
- `AIza`
- `xai-`
- `sbp_`
- `eyJ`
- `supabase.co`
- `localhost`
- `127.0.0.1`
- `/api/knowledge-graph`
- `/api/code`

### PII Patterns

- Email addresses
- Phone numbers

### Infrastructure Patterns

- `supabase.co`
- `localhost`
- `127.0.0.1`
- `/api/knowledge-graph`
- `/api/code`

### External Resource Patterns

- `external_script`
- `external_font`
- `analytics`
- `external_url`