# Avalanche Insight Hub — Public Knowledge Graph & Map Learning Site

A public, static, educational website for exploring the Avalanche Insight Hub codebase structure and avalanche forecasting concepts.

## Quick Start

```bash
# Install dependencies
npm ci

# Build
npm run build

# Test
npm run test

# Verify public safety
python3 scripts/verify_public_safety.py

# Sanitize built output
python3 scripts/sanitize_output.py

# Preview locally
npm run preview -- --host 127.0.0.1 --port 4173
```

## What This Site Contains

1. **Code Knowledge Graph** — 4,926 nodes / 8,183 edges, interactive canvas visualization, 7 perspectives, search, table view, deterministic explanations
2. **Avalanche Forecast Map** — Currently BLOCKED (no approved static snapshot). Shows explicit blocked state.
3. **About Page** — Limitations, attribution, MIT license, provenance

## Safety Guarantees

- No backend, no API calls, no AI endpoints
- No external map tiles, fonts, or CDN resources
- Strict CSP: `default-src 'self'; connect-src 'self'` (same-origin static data only)
- Field allowlists on all graph data
- PII redaction with fail-closed behavior
- Public safety verification script

## Status

- **Graph export:** `approved` (clean scoped source snapshot; content approval recorded)
- **Map:** `blocked` (no approved static snapshot)
- **Public content approval:** `APPROVED_PUBLIC_CONTENT` recorded

## Documentation

- [Public Content Policy](docs/PUBLIC_CONTENT_POLICY.md)
- [Public Release Checklist](docs/PUBLIC_RELEASE_CHECKLIST.md)
- [Site Architecture](docs/SITE_ARCHITECTURE.md)
- [Update and Rollback](docs/UPDATE_AND_ROLLBACK.md)
- [Source Candidate Report](handoff/SOURCE_CANDIDATE_REPORT.md)
- [Public Content Review Packet](handoff/PUBLIC_CONTENT_REVIEW_PACKET.md)
- [Map Input Request](handoff/MAP_INPUT_REQUEST.md)
- [Build Evidence](handoff/BUILD_EVIDENCE.md)
- [GLM Handoff](handoff/GLM_HANDOFF.md)

## License

MIT — see [public/NOTICE](public/NOTICE) and [public/ATTRIBUTION.md](public/ATTRIBUTION.md)
