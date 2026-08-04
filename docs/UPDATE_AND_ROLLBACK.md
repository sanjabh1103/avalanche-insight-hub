# Update and Rollback

## Updating the Graph

When the source codebase changes and a new graph snapshot is needed:

1. **Verify source state:** use the approved clean scoped source snapshot, not an arbitrary dirty checkout.
   ```bash
   git -C /path/to/clean-scoped-source log --oneline -1
   git -C /path/to/clean-scoped-source status --short | wc -l
   ```

2. **Export an approved snapshot (0 non-generated dirty entries):**
   ```bash
   cd /Users/sanjayb/avalanche-insight-hub-public-knowledge-site
   python3 scripts/export_graph.py \
     --source-root /path/to/clean-scoped-source \
     --status approved \
     --owner-approval APPROVED_PUBLIC_CONTENT
   python3 scripts/generate_explanations.py
   npm run build
   python3 scripts/verify_public_safety.py
   python3 scripts/sanitize_output.py
   ```

3. **If source is dirty:**
   - A dirty source export will be marked `preview_only` and must not be deployed
   - Public release remains blocked
   - Record the dirty state in `handoff/SOURCE_CANDIDATE_REPORT.md`

## Updating the Map

When an approved static map snapshot becomes available:

1. Place the approved snapshot at `public/data/forecast-map.json` with the schema defined in `public/data/forecast-map-manifest.json`
2. Set `status` to `"approved"` in both files
3. Run the sanitizer and public safety verification
4. Implement the map rendering component (currently only blocked state is implemented)

## Rollback

### Version Information to Record

Before deploying, record:

| Item | Value |
|---|---|
| Source HEAD | `f582d1822b3994a6d10832e66e085ab58c8304f4` |
| Graph content hash | `cc26ff2f74f49fc3632cb2ba1b8504bde2e18d430e8f07348db8c018b9c3a040` |
| Graph file SHA-256 | `df77d44e305e0877c4024e343b93da2c29ac7bf2dea9402e3ae1d0588caf3224` |
| Export status | `approved` |
| Map status | `blocked` |

### Rollback Procedure

1. **Revert to previous build:**
   ```bash
   # If using git:
   git log --oneline  # find previous commit
   git checkout <previous-commit> -- dist/
   # Or rebuild from previous source:
   npm run build
   ```

2. **Verify rollback:**
   ```bash
   python3 scripts/verify_public_safety.py
   python3 scripts/sanitize_output.py
   npm run preview -- --host 127.0.0.1 --port 4173
   # Verify in browser
   ```

3. **Update provenance:**
   - Update `handoff/SOURCE_CANDIDATE_REPORT.md` with rollback info
   - Record rollback timestamp and reason

## Deployment Platforms

The `dist/` directory can be deployed to any static site host:

- **GitHub Pages:** Push `dist/` to `gh-pages` branch
- **Netlify:** Drag `dist/` to Netlify dashboard or use CLI
- **Vercel:** `vercel --prod` from project root
- **Cloudflare Pages:** Connect repo, set build command to `npm run build`, output to `dist/`

## Post-Deployment Verification

After deploying to a public URL:

1. Verify all 3 pages load (/, /graph, /map, /about)
2. Open browser DevTools → Network tab
3. Verify NO external network requests (only same-origin fetches for /data/*.json)
4. Verify CSP is active (check console for CSP violations)
5. Verify graph loads and is interactive
6. Verify map shows blocked state
7. Verify no console errors
