# AGENTS.md — Public Knowledge Site

> This is a separate, public-facing static website project. It is NOT part of the main Avalanche Insight Hub application.

## Rules

1. **No secrets** — this is a public site. Never add credentials, API keys, tokens, or private endpoints.
2. **No backend** — static-only. No server-side code, no API routes, no database connections.
3. **No external resources** — no external map tiles, fonts, scripts, or CDN resources. All assets must be same-origin.
4. **No AI endpoints** — explanations are deterministic and pre-generated. No Gemini, OpenAI, or other AI API calls.
5. **Pinned dependencies** — all npm packages are pinned to specific versions. No floating ranges (no `^` or `~`).
6. **Sanitized data only** — the graph data uses strict field allowlists. Do not import raw source data.
7. **No fabricated map data** — the map is blocked. No synthetic or fabricated forecast data is permitted.
8. **Source repo is read-only** — `/Users/sanjayb/avalanche-insight-hub` is input only. All writes go to this project.
9. **CSP enforced** — `connect-src 'self'` allows same-origin fetches only. No external connections.
10. **Fail-closed sanitizer** — any forbidden content finding blocks the build.

## Build Commands

```bash
npm ci
npm run lint
npm run build
npm run test
npm run preview
```

## Verification Commands

```bash
python3 scripts/verify_public_safety.py
python3 scripts/sanitize_output.py
```

## Architecture

- Vite + React + TypeScript (no backend)
- Graph data: static JSON in `public/data/code-graph.json`, fetched at runtime via same-origin fetch
- Map data: `public/data/forecast-map.json` — status is `blocked`, no cells
- Explanations: pre-generated JSON in `public/data/explanations.json`
- Graph visualization: custom canvas renderer (no external graph library)
- Map: blocked state UI (no renderer implemented — no approved snapshot exists)
- CSP: `default-src 'self'; connect-src 'self'` — allows same-origin data fetches, blocks all external connections
