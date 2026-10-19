# Public Content Policy

## Audience

Public internet — all content is accessible to anyone with the URL.

## Site Purpose

Educational codebase knowledge graph and avalanche/forecast map explanation. This site helps learners understand the structure of the Avalanche Insight Hub codebase and avalanche forecasting concepts.

## Map Data Policy

- Map data must be a static snapshot from an approved, rights-cleared source.
- The map must never display live or real-time forecast data.
- Every map display must show: source, valid-from, valid-to, uncertainty, and limitations.
- If no approved snapshot exists, the map must show an explicit `MAP_SNAPSHOT_NOT_AVAILABLE` blocked state.
- No fabricated or synthetic map data is permitted.

## Operational Safety Disclaimer

This site is **not** an operational safety decision system. It must not be used for:
- Avalanche route planning
- Go/no-go decisions in avalanche terrain
- Real-time risk assessment
- Any safety-critical decision

## Personal Data Policy

- No personal data is allowed: names, emails, phone numbers, addresses, personal identifiers.
- No private observation data is allowed: observation IDs, sensor IDs, station IDs.
- No customer data is allowed.

## Backend Policy

- No live backend/API calls are allowed in v1.
- No Supabase, Gemini, OpenAI, or other runtime service calls.
- No live map tiles (CARTO, OpenStreetMap, etc.).
- All data must be static JSON files served from the same origin.

## Publication Policy

- Public publication requires explicit human approval after sanitizer review.
- The approval must be the exact response: `APPROVED_PUBLIC_CONTENT`.
- Silence, partial feedback, or generic "looks good" must not be interpreted as approval.
- If approval is not received, the site remains in preview-only mode.

## Sanitizer Policy

- The sanitizer must fail closed: any detection of secrets, PII, private IDs, or unsafe content blocks the build.
- Sanitizer rules must not be weakened to make the build pass.
- The sanitizer must scan both source inputs and generated site output.

## Licensing Policy

- Every asset (graph, map, library, font, icon, image) must have documented source, license, and attribution.
- If licensing is unknown, the asset must be excluded and the relevant feature blocked.
- CARTO and other tile services are not automatically licensed for public use.
