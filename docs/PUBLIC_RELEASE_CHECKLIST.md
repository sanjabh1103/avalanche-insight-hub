# Public Release Checklist

## Pre-Release Gates

- [ ] Source candidate report created (`handoff/SOURCE_CANDIDATE_REPORT.md`)
- [ ] Graph export complete (`public/data/code-graph.json`)
- [ ] Graph manifest complete (`public/data/code-graph-manifest.json`)
- [ ] Graph field allowlist enforced (no unknown fields)
- [ ] Graph canonical hash computed and recorded
- [ ] Graph dangling edges rejected
- [ ] Map snapshot approved OR blocked state active (`public/data/forecast-map.json`)
- [ ] If map is blocked: `handoff/MAP_INPUT_REQUEST.md` created
- [ ] Sanitizer run on source inputs — PASS
- [ ] Sanitizer run on built output — PASS
- [ ] No secrets, PII, private IDs, or unsafe content detected
- [ ] Attribution files created (`public/ATTRIBUTION.md`, `public/NOTICE`)
- [ ] Source ledger created (`public/data/source-ledger.json`)
- [ ] All licenses documented
- [ ] CSP header present in HTML
- [ ] No external scripts, fonts, or API calls
- [ ] Build succeeds (`npm run build`)
- [ ] Tests pass (`npm run test`)
- [ ] Public safety verification passes (`python3 scripts/verify_public_safety.py`)
- [ ] Browser smoke test completed
- [ ] No external network requests at runtime (only same-origin static data fetches, verified in DevTools)
- [ ] Content review packet created (`handoff/PUBLIC_CONTENT_REVIEW_PACKET.md`)
- [ ] Human approval received: `APPROVED_PUBLIC_CONTENT`

## Deployment Steps (Final 10% — Human Only)

- [ ] UI polish complete
- [ ] Static site host configured (GitHub Pages, Netlify, Vercel, Cloudflare Pages)
- [ ] Version saved and reviewed
- [ ] Deployed to public URL
- [ ] Public URL smoke test passed
- [ ] Rollback info recorded (source HEAD, graph SHA-256, map SHA-256)

## Post-Release

- [ ] Public URL verified
- [ ] No external requests confirmed on live URL
- [ ] Rollback procedure documented
