# Code Knowledge Graph — Exploration Guide

> **For:** Developers onboarding to the Avalanche Insight Hub codebase
> **Prerequisites:** Node.js 22+, npm, git
> **Time to complete:** 30–45 minutes
> **Access level:** Local development only (no Supabase credentials needed)

---

## Where to Onboard

This repository is the **public cron execution repo** — it runs scheduled ML pipeline jobs only. For full onboarding, use these three surfaces:

1. **For full docs and graphify access:** Clone the private repo (`sanjabh11/avalanche-insight-hub`) and read `docs/ONBOARDING_GUIDE.md` (novice) and `docs/SCIENTIST_ARCHITECTURE_BRIEF.md` (scientist). The private repo has the full graphify graph (~19,968 nodes) and all deliverables.
2. **For visual graph browsing:** Visit the Public Knowledge Site at **https://dist-silk-sigma-21.vercel.app** — a static site with two graph systems:
   - **Structural Graph** (5,076 nodes, 8,434 edges) — the built-in KS graph with search, perspectives, table view, and deterministic explanations. Available at `/graph`.
   - **Graphify Visualizations** (19,968 nodes, 37,870 edges, 1,208 communities) — the full Graphify knowledge graph with 3 interactive views at `/graphify/`:
     - `/graphify/graph.html` — Force-directed network graph (vis-network, 20MB)
     - `/graphify/tree.html` — Collapsible file/function tree (D3 v7, 1.5MB)
     - `/graphify/callflow.html` — Architecture call-flow diagrams (Mermaid, 380KB)
   - No CLI or credentials needed for either.
3. **For Graphify CLI access (advanced):** Install graphify (`uv tool install graphify`), clone the private repo, and run:
   ```bash
   graphify .                    # Build graph from code (AST + LLM, ~10s for AST-only)
   graphify god-nodes --top 10   # Most connected nodes
   graphify path "main()" "upsert_forecast_grid()"  # Golden path trace
   graphify explain "HimalayanAccuracyContractTests"  # Node explanation
   graphify affected "SnowpackProxy" --depth 2  # Blast radius
   graphify tree                 # Generate GRAPH_TREE.html
   graphify export callflow-html # Generate callflow HTML
   ```
4. **For cron execution (this repo):** Run `python3 scripts/verify_schedule_contract.py` to verify the cron schedule. This repo is runners-only — do not run graphify or frontend dev servers here.

### Redeploy Runbook (Knowledge Site + Graphify)

After a graph refresh or code change, redeploy the KS with both graph systems:

```bash
# 1. Refresh the structural graph (private repo)
cd ~/avalanche-insight-hub
bash scripts/refresh_knowledge_graph_structural.sh

# 2. Scrub + regenerate Graphify HTML (private repo)
python3 scripts/scrub_graphify_graph.py

# 3. Export the structural graph to KS
cd ~/avalanche-insight-hub-public-knowledge-site
python3 scripts/export_graph.py

# 4. Copy scrubbed Graphify HTML to KS
cp ~/avalanche-insight-hub/graphify-out/graph.html dist/graphify/graph.html
cp ~/avalanche-insight-hub/graphify-out/GRAPH_TREE-scrubbed.html dist/graphify/tree.html
cp ~/avalanche-insight-hub/graphify-out/avalanche-callflow-scrubbed.html dist/graphify/callflow.html

# 5. Verify public safety (checks both structural + graphify)
python3 scripts/verify_public_safety.py

# 6. Build + test + lint
npm run build && npm run test && npm run lint

# 7. Copy HTML again (build may overwrite dist/graphify/)
cp ~/avalanche-insight-hub/graphify-out/graph.html dist/graphify/graph.html
cp ~/avalanche-insight-hub/graphify-out/GRAPH_TREE-scrubbed.html dist/graphify/tree.html
cp ~/avalanche-insight-hub/graphify-out/avalanche-callflow-scrubbed.html dist/graphify/callflow.html

# 8. Deploy to Vercel
vercel deploy dist/ --prod --yes
```

**Graph freshness:** The Graphify graph was built at commit `91b772f` (2026-08-07).
The structural graph was refreshed at commit `e324dcb7` (2026-08-07).
To check staleness: `graphify check-update .` in the private repo.

---

## What You'll See

An interactive knowledge graph of the entire codebase — **5,076 nodes** (files, functions, classes) connected by **8,434 edges** (imports, calls, containment, test coverage). You can explore it visually or as a searchable table, switch between 6 architectural perspectives, and read deterministic explanations of every node. The Graphify visualizations at `/graphify/` provide a deeper view with 19,968 nodes including rationale, concepts, and documents.

---

## Phase 1: Setup (5 minutes)

### Step 1.1 — Clone the repository

```bash
git clone https://github.com/sanjabh11/avalanche-insight-hub.git
cd avalanche-insight-hub
```

### Step 1.2 — Install dependencies

```bash
npm install
```

This installs ~400 packages. Wait for it to complete.

### Step 1.3 — The structural graph

The current candidate working tree contains a **Phase 2 structural graph** (4,916 nodes, 8,158 edges) that works without the Understand plugin. In this checkout the graph and manifest are still untracked, so they are **not yet guaranteed to appear in a clean `git clone`**. Until the release candidate is committed, a clean clone will use the older bundled fallback instead.

**To regenerate the graph from source** (optional, after significant code changes):

```bash
bash scripts/refresh_knowledge_graph_structural.sh
```

**Prerequisites for rebuild:**
- The Understand Anything plugin must be installed at `$HOME/.understand-anything/repo/understand-anything-plugin`. This is an internal tool — ask Sanjay for setup instructions.
- Python 3.10+ must be available on your PATH.
- The script builds the graph from the current source tree, so run it after any significant code changes.

**If you don't have the Understand plugin:** The committed fallback graph will load when present. The graph UI, perspectives, and deterministic explanations will function. The "Rebuild locally" button will fail gracefully with a status message. You do not need the plugin to view or explore a committed snapshot.

**What the script does:**
1. Scans the codebase using the Understand plugin's structural analysis
2. Generates `.understand-anything/phase2-structural-graph.json` (4,916 nodes, 8,158 edges)
3. Generates `.understand-anything/phase2-structural-manifest.json` (commit, hashes, timestamp)
4. These files must be committed as part of the knowledge-graph release candidate — regeneration alone only updates the working tree

### Step 1.4 — Create local environment file

Create a file named `.env.local` in the project root with this single line:

```
VITE_DEMO_MODE=true
```

This bypasses the scientist login gate **only in local dev**. It has no effect in production builds. The file is gitignored and will never be committed.

> **Why?** The knowledge graph route is protected by a role-based access gate (`RoleAccessGate`) that requires a Supabase scientist account. Demo mode bypasses this for local exploration so you don't need credentials.

### Step 1.5 — Start the dev server

```bash
npm run dev
```

You should see output like:

```
  VITE v7.x.x  ready in 500 ms
  ➜  Local:   http://localhost:8080/
```

### Step 1.6 — Open the knowledge graph

Open your browser to:

```
http://localhost:8080/knowledge
```

You should see the **Code Knowledge Graph** page with a "Local only" badge and stats showing node/edge/layer/tour counts.

> **If you see a login screen instead:** The `.env.local` file is missing or `VITE_DEMO_MODE` is not set to `true`. Stop the server (`Ctrl+C`), create the file, and restart.

> **If you see "Local Knowledge Workspace" with a lock icon:** You're not on localhost. The graph only works on `localhost`, `127.0.0.1`, or `::1`. It will NOT work over a network IP.

---

## Phase 2: Understanding the Interface (5 minutes)

When you open the graph, you'll see:

### Header Area (top)
| Element | What it does |
|---|---|
| **"Code Knowledge Graph" title** | Page identifier |
| **"Local only" badge** | Confirms you're in local dev mode |
| **Stats line** | Shows node count, edge count, layer count, tour step count |
| **Graph/Table toggle** | Switches between visual graph and accessible table view |
| **Info button (ⓘ)** | Shows/hides an info panel about the graph |

### Perspective Switcher (below header)
Six tabs that filter the graph to show different architectural views:
| Icon | Perspective | What it shows |
|---|---|---|
| Network | Architecture | Full codebase structure — all files, imports, containment |
| Brain | ML Pipeline | The active forecast path: RF model, features, training, inference |
| GitBranch | Data Flow | How data moves: ingestion → features → model → output |
| ShieldCheck | Security & Gates | Verification gates, denylist zones, auth, safety thresholds |
| FlaskConical | Tests | Test coverage: which source files have tests |
| FileCheck | Release & Evidence | Artifacts, manifests, governance, release evidence chain |

### Audience & Depth Controls (below perspectives)
| Control | Options | What it changes |
|---|---|---|
| **Audience** | Novice, ML expert, Technical customer | Changes the explanation emphasis when you click a node |
| **Depth** | Briefing, Working, Deep | Changes how much detail and caveats are shown |

### Provenance Card (bottom of header)
Shows the graph hash, freshness status, and whether the worktree is dirty. This tells you if the graph is current or stale.

### Main Content Area
- **Graph view:** Interactive hierarchical graph using ReactFlow + dagre layout. Nodes are color-coded by type, edges are color-coded by relationship.
- **Table view:** Searchable, expandable table of all nodes with their relationships. Better for screen readers and keyboard navigation.

---

## Phase 3: Exploring the Graph View (10 minutes)

### Step 3.1 — Start with the Architecture perspective

1. Click the **Network** (Architecture) tab if not already selected
2. You'll see the full codebase as a hierarchical graph
3. **Node colors:**
   - 🔵 Blue = file
   - 🟢 Green = function
   - 🟡 Amber = class
   - 🟣 Purple = pipeline (semantic)
   - ⚪ Gray = config (semantic)

4. **Edge colors:**
   - Slate gray = contains (file contains function/class)
   - Sky blue = imports (file imports another file)
   - Orange = calls (function calls another function)
   - Green = tested_by (file tested by test file)

### Step 3.2 — Navigate the graph

| Action | How |
|---|---|
| **Pan** | Click and drag the background |
| **Zoom** | Scroll wheel, or use +/− controls |
| **Fit to view** | Click the fit button (□) in the controls |
| **Select a node** | Click any node — it highlights and opens the detail panel |
| **Minimap** | Bottom-right corner shows the full graph with current viewport |

### Step 3.3 — Click a node to see its explanation

1. Click any node (e.g., a blue file node like `backend/common/abc_optimizer.py`)
2. The **Node Detail Panel** opens on the right side
3. You'll see:
   - Node type badge (FILE, FUNCTION, CLASS)
   - File path
   - Node name
   - Perspective label
   - **Explanation sections** with headings and markdown-formatted body
   - Source reference badges
   - Footer showing audience, depth, and proof level
   - "Rule-based, no LLM" notice

4. The explanation is **deterministic** — it's generated by rules, not an AI model. It uses the graph structure, perspective, audience, and depth you selected.

### Step 3.4 — Switch perspectives to see different views

1. Click **ML Pipeline** (Brain icon)
2. Notice how the graph filters to only show ML-related nodes
3. Non-highlighted nodes dim to 35% opacity
4. The node count badge on each perspective tab shows how many nodes match

5. Try each perspective:
   - **Data Flow** — see how data moves through the system
   - **Security & Gates** — see verification and safety nodes
   - **Tests** — see test coverage relationships
   - **Release & Evidence** — see artifact and release nodes

### Step 3.5 — Change audience and depth

1. With a node selected, change the **Audience** dropdown to "ML expert"
2. The explanation sections change to show: labels/features, splits/leakage, metrics/calibration, SHAP/artifact provenance
3. Change **Depth** to "Deep" — explanations get longer with more caveats and provenance detail
4. Try "Technical customer" audience — shows interfaces/ownership, SLO/reliability, RBAC/observability, licensing/integration

---

## Phase 4: Exploring the Table View (5 minutes)

### Step 4.1 — Switch to table view

1. Click the **Table** icon (next to the Graph icon in the header)
2. You'll see a searchable table of all nodes

### Step 4.2 — Search for nodes

1. Type in the search bar (e.g., "forecast", "model", "auth", "verification")
2. The table filters by node name, path, summary, and tags
3. Results update live as you type

### Step 4.3 — Expand relationships

1. Click the expand arrow (▶) on any row that has relationships
2. You'll see all incoming and outgoing edges for that node
3. Each relationship shows:
   - Edge type badge (contains, imports, calls, tested_by)
   - Direction (to/from)
   - Related node name (clickable to navigate)
   - Related node path

### Step 4.4 — Select a node from the table

1. Click any node name in the table
2. The Node Detail Panel opens on the right (same as graph view)
3. You can navigate between graph and table views seamlessly

---

## Phase 5: Guided Tour — Key Nodes to Explore (10 minutes)

Follow this ordered tour to understand the codebase architecture:

### Stop 1: The ML Forecast Pipeline
1. Switch to **ML Pipeline** perspective
2. Search for `daily_inference` in the table view
3. Click the node — read the explanation
4. This is the main entry point for avalanche forecasting

### Stop 2: Feature Engineering
1. Stay in ML Pipeline perspective
2. Search for `abc_optimizer` or `feature`
3. Explore the functions that build features for the model
4. Notice the `calls` edges — these show the feature engineering chain

### Stop 3: Verification Gates
1. Switch to **Security & Gates** perspective
2. Search for `verification` or `conformance`
3. These nodes show how the system validates its own outputs
4. Note: Some files are intentionally excluded (denylist zones) for safety

### Stop 4: Test Coverage
1. Switch to **Tests** perspective
2. Search for `test_` to see test files
3. Expand any test node to see what it tests (tested_by edges)
4. This shows which source files have test coverage

### Stop 5: Data Ingestion
1. Switch to **Data Flow** perspective
2. Search for `ingest` or `field_report`
3. These nodes show how data enters the system
4. Follow the `calls` edges to see the data processing chain

### Stop 6: Release Evidence
1. Switch to **Release & Evidence** perspective
2. Search for `manifest` or `artifact`
3. These nodes show the release governance chain
4. This is how the system proves its outputs are trustworthy

---

## Phase 6: Understanding the Provenance System (5 minutes)

### Step 6.1 — Read the provenance card

At the bottom of the header, the provenance card shows:
| Field | Meaning |
|---|---|
| **Graph hash** | SHA-256 hash of the graph data — changes when the graph is rebuilt |
| **Freshness** | `current` (graph matches latest commit) or `stale` (graph is behind) |
| **Worktree dirty** | `true` if there are uncommitted changes that might not be in the graph |

### Step 6.2 — Understand proof levels

When you click a node, the detail panel footer shows a proof level:
| Level | Meaning |
|---|---|
| **snapshot-linked** | The explanation is backed by a verified graph snapshot with hash |
| **unverified** | The explanation is from the bundled graph without live verification |

### Step 6.3 — Understand claim categories

Each explanation section has a claim category:
| Category | Meaning |
|---|---|
| **fact** | Verified by snapshot and current |
| **inference** | Interpretive but backed by evidence |
| **plan** | Forward-looking, backed by evidence |
| **stale** | Graph is behind current code — may be outdated |
| **blocked** | No verified evidence available |
| **unsupported** | No evidence backing |

---

## Phase 7: Keyboard Navigation (for accessibility)

| Key | Action |
|---|---|
| **Tab** | Move between interactive elements |
| **Arrow Left/Right** | Switch perspectives (when focus is on perspective switcher) |
| **Home/End** | First/last perspective |
| **Enter** | Select focused node or button |
| **Escape** | Close detail panel |
| **Ctrl+0** | Reset zoom (in graph view) |

---

## What You Cannot Do (and Why)

| Limitation | Reason |
|---|---|
| **No AI model explanations** | The model endpoint requires Supabase + Gemini API key + scientist role. You get deterministic rule-based explanations only. |
| **No live source code viewing** | The `/api/code` endpoint works only on localhost with the dev server running. It is available but limited to allowlisted directories. |
| **No editing** | The graph is read-only. It's a snapshot of the codebase at a specific commit. |
| **No access to denylist zones** | 8 safety-critical files/directories are excluded from the graph entirely. You won't see nodes for `risk_math.py`, `verification_exit_gates.py`, etc. |
| **Graph may be stale** | The Phase 2 snapshot is tied to its manifest commit and may be generated from a dirty working tree. Check the provenance card and release status before treating it as a clean-checkout baseline. |

---

## Troubleshooting

| Problem | Solution |
|---|---|
| **Login screen appears** | Create `.env.local` with `VITE_DEMO_MODE=true` and restart `npm run dev` |
| **"Local Knowledge Workspace" lock page** | You're not on localhost. Use `http://localhost:8080/knowledge` not a network IP |
| **Blank page** | Check browser console (F12). Ensure Node.js 22+ is installed. Try `rm -rf node_modules && npm install` |
| **Graph is empty** | Wait for the graph JSON to load (it's code-split and loads asynchronously). Check the Network tab in DevTools. |
| **Port 8080 is in use** | The dev server will auto-increment to 8081, 8082, etc. Check the terminal output for the actual port. |
| **Node detail panel shows "Error"** | Refresh the page. If it persists, check that the graph JSON loaded successfully in the Network tab. |

---

## 15-Minute Learner Path

Follow these steps in order to get a complete tour of the knowledge graph in 15 minutes. No prior knowledge of the codebase is required.

### Minutes 0–3: Start the app

1. Open a terminal in the project root
2. Run `npm install` (if not already done)
3. Create `.env.local` with `VITE_DEMO_MODE=true` (if not already done)
4. Run `npm run dev`
5. Open `http://localhost:8080/knowledge` in your browser

You should see the knowledge graph page with a graph visualization, not a lock screen.

### Minutes 3–5: Explore the Architecture perspective

1. The default perspective is **Architecture** — this shows files, functions, and classes
2. Scroll and zoom to explore the graph. Each node is a file, function, or class
3. Notice the provenance card at the top — it shows the graph commit, node count, and freshness status

### Minutes 5–8: Switch to ML Pipeline perspective

1. Click the **ML Pipeline** button in the perspective switcher
2. The graph filters to show only ML-related nodes — training, inference, feature engineering
3. Notice how the node count changes — fewer nodes, focused on the ML pipeline
4. Try clicking a node to see its details in the right panel

### Minutes 8–10: Switch to Table view

1. Click the **Table** toggle button (near the perspective switcher)
2. The graph switches to a searchable, sortable table view
3. Use the search box to find files by name (e.g., type "model" or "forecast")
4. Click a row to select that node and see its details

### Minutes 8–10: Read the provenance card

1. Look at the provenance card at the top of the page
2. It shows:
   - **Graph commit**: the git commit the graph was built from
   - **Checkout**: the current git commit
   - **Source**: whether the graph came from the local API or bundled fallback
   - **Status**: "Current snapshot", "Stale snapshot", or "Snapshot context changed"
3. If the status is "Stale", the graph was built from an older commit — that's OK for learning

### Minutes 10–13: Try Audience and Depth controls

1. Select a node by clicking it in the graph or table
2. In the node detail panel, find the **Audience** selector
3. Switch between **Novice**, **ML Expert**, and **Technical Customer**
4. Notice how the explanation changes tone and detail level
5. Find the **Depth** selector and switch between **Briefing**, **Working**, and **Deep**
6. The explanation expands or contracts based on the depth

### Minutes 13–15: Reload and explore more

1. Click the **Reload snapshot** button to refresh the graph from the local API
2. Try switching to other perspectives: **Data Flow**, **Security**, **Tests**, **Release**
3. Each perspective shows a different slice of the codebase, filtered by relevant edge types
4. When you're done, close the browser tab and stop the dev server with `Ctrl+C`

### What you've learned

In 15 minutes, you've:
- Seen the entire codebase as a structural graph (4,916 nodes)
- Explored 6 different architectural perspectives
- Inspected individual files, functions, and classes
- Read provenance metadata (commit, freshness, source)
- Adjusted explanations for different audiences and depths
- Verified the graph is current and loaded from the local API

---

## Quick Reference Card

```
URL:           http://localhost:8080/knowledge
Login bypass:  .env.local → VITE_DEMO_MODE=true
Start server:  npm run dev
Graph size:    4,916 nodes, 8,158 edges, 0 layers, 0 tours (structural snapshot)
Perspectives:  6 (Architecture, ML Pipeline, Data Flow, Security, Tests, Release)
Audiences:     3 (Novice, ML Expert, Technical Customer)
Depths:        3 (Briefing, Working, Deep)
Explanations:  Deterministic (rule-based, no AI model)
Source code:   Not exposed (loopback API only, limited to allowlisted dirs)
Denylist:      8 safety-critical paths excluded from graph
```

---

## Next Steps After Exploration

1. **Read the README** — `https://github.com/sanjabh1103/avalanche-insight-hub` for the public architecture overview
2. **Explore the code** — Use the graph to find files, then open them in your editor
3. **Run the tests** — `npm run test` to see 375+ tests covering the frontend
4. **Check the backend** — `python -m unittest discover -s backend/tests -p 'test_*.py'` for Python tests
5. **Read AGENTS.md** — In the repo root, explains the operating manual and denylist zones

---

## Enabling AI-Powered Explanations (Optional)

The knowledge graph has two explanation engines:

1. **Deterministic (rule-based)** — Active by default. Produces structured explanations from node metadata, graph relationships, and source code snippets. No LLM required. 138 tests cover this path.

2. **AI-powered (Gemini 3.5 Flash)** — Disabled by default. Adds natural-language Q&A, cross-node synthesis, and audience-adaptive tone. Requires Supabase backend setup.

### How to Switch Between Engines

In the **Node Detail Panel** (right side of the graph view), there is a toggle labeled **"Use AI explanations"** with a sparkle icon. Toggle it on to switch to Gemini-powered explanations. When AI mode is on:

- An optional **question input** appears — type any question about the selected node and press **Ask**
- The panel sends the request to the Supabase Edge Function, which calls Gemini with the server-owned graph context
- If the AI endpoint is unavailable (not configured, rate limited, or network error), the panel **automatically falls back** to the deterministic engine and shows an amber warning

### Prerequisites to Enable AI Mode

The AI endpoint requires a Supabase project with migrations applied and secrets configured. Here are all 7 steps:

#### Step 1: Apply Database Migrations

```bash
# From the repo root, apply the two knowledge-graph migrations:
supabase db push

# Or manually apply just the KG migrations:
supabase migration up --file supabase/migrations/20260806120000_knowledge_graph_model_endpoint.sql
supabase migration up --file supabase/migrations/20260807120000_create_knowledge_graph_snapshot_bucket.sql
```

This creates:
- `model_endpoint_audit` — append-only audit log (RLS: users see own entries, service role inserts)
- `model_endpoint_rate_limits` — per-user sliding window (default: 50 requests/hour)
- `model_endpoint_quotas` — per-user monthly token/cost quotas (default: 100K tokens, $10/month)
- `model_endpoint_cache` — SHA-256 keyed response cache (cache hits don't consume rate limit)
- `gemini_usage_reservations` — global spend cap (prevents runaway costs)
- `knowledge_graph_snapshots` storage bucket — private, 50MB max, JSON only
- RPCs: `reserve_model_usage()`, `reserve_gemini_usage()`, `check_rate_limit()`

#### Step 2: Deploy the Edge Function

```bash
# Deploy the knowledge-graph-model edge function:
supabase functions deploy knowledge-graph-model
```

> Note: The function's `verify_jwt = true` setting in `supabase/config.toml` ensures the Supabase platform rejects unauthenticated requests at the gateway level (defense-in-depth). The function also verifies JWT in its own code as a second layer. Do NOT use `--no-verify-jwt` — it would bypass the platform-level gate.

#### Step 3: Set Supabase Secrets

```bash
# Master on/off switch:
supabase secrets set KNOWLEDGE_GRAPH_MODEL_ENABLED=true

# Google AI Studio Gemini API key (get from https://aistudio.google.com/apikey):
supabase secrets set GEMINI_API_KEY=AIzaSy...your-key...

# Snapshot ID (a UUID you choose — must match the folder name in Step 5):
supabase secrets set KNOWLEDGE_GRAPH_SNAPSHOT_ID=2026-08-03-v1

# Optional: CORS origins (comma-separated, default is null = same-origin only):
supabase secrets set ALLOWED_ORIGINS=http://localhost:8080,https://avalanche-insight-hub.netlify.app

# Optional: Rate limit is configured in the model_endpoint_rate_limits table (default: 50 req/hour).
# To change it, update the database row for a user or modify the migration default.
# There is no RATE_LIMIT_PER_USER env var — the rate limit is database-driven.

# Optional: Gemini model name (default: gemini-3.5-flash — GA, no shutdown date):
supabase secrets set GEMINI_MODEL_NAME=gemini-3.5-flash
```

#### Step 4: Build the Knowledge Graph Snapshot

```bash
# Run the structural snapshot builder:
python3 scripts/build_structural_knowledge_snapshot.py --root . --intermediate .understand-anything/intermediate

# This produces:
#   .understand-anything/phase2-structural-manifest.json  (snapshot metadata)
#   .understand-anything/phase2-structural-graph.json      (structural graph)
```

#### Step 5: Upload the Snapshot to Supabase Storage

```bash
# Create the snapshot folder in the private bucket:
# The folder name MUST match KNOWLEDGE_GRAPH_SNAPSHOT_ID from Step 3.

# Upload manifest.json:
supabase storage upload knowledge-graph-snapshots/<SNAPSHOT_ID>/manifest.json \
  .understand-anything/phase2-structural-manifest.json

# Upload graph.json:
supabase storage upload knowledge-graph-snapshots/<SNAPSHOT_ID>/graph.json \
  .understand-anything/phase2-structural-graph.json
```

> **Note:** Replace `<SNAPSHOT_ID>` with the actual snapshot ID (e.g., `phase2-structural-fallback-v2`).
> The snapshot ID in the storage path must match the `KNOWLEDGE_GRAPH_SNAPSHOT_ID` secret.
> You can also upload via the Supabase Dashboard → Storage → `knowledge-graph-snapshots` bucket.

#### Step 6: Create a Scientist User

The edge function requires `scientist` or `admin` role. To assign a role:

```bash
# In the Supabase SQL editor, run:
-- Create or update a user's role
UPDATE auth.users
SET raw_user_meta_data = raw_user_meta_data || '{"role": "scientist"}'::jsonb
WHERE email = 'colleague@example.com';
```

Or use the Supabase Dashboard → Authentication → Users → select user → edit metadata → add `"role": "scientist"`.

#### Step 7: Verify the Endpoint

```bash
# Test with curl (replace with your Supabase URL and a valid JWT):
curl -X POST \
  https://YOUR_PROJECT.supabase.co/functions/v1/knowledge-graph-model \
  -H "Authorization: Bearer YOUR_JWT" \
  -H "Content-Type: application/json" \
  -d '{"nodeId": "src/App.tsx", "perspective": "architecture", "context": {"audience": "novice", "depth": "briefing"}}'

# Expected response:
# {
#   "requestId": "...",
#   "timestamp": "...",
#   "userRole": "scientist",
#   "explanation": { "summary": "...", "sections": [...] },
#   "modelUsage": { "provider": "google", "model": "gemini-3.5-flash", "tokensUsed": 123, "costUsd": 0.0008, "inputTokens": 80, "outputTokens": 43, "usageSource": "provider" },
#   "security": { "denylistViolations": [], "secretsRedacted": false, "rateLimitRemaining": 49 }
# }
```

### Security Layers (15 total)

When AI mode is enabled, every request passes through 15 security layers:

| # | Layer | What It Does |
|---|---|---|
| 1 | CORS lockdown | Default `null` origin; operator sets `ALLOWED_ORIGINS` |
| 2 | JWT verification | Rejects unauthenticated requests |
| 3 | RBAC | Requires `scientist` or `admin` role |
| 4 | Request validation | Rejects null bytes, oversized inputs, non-object body |
| 5 | Perspective allowlist | Only 6 valid perspectives accepted |
| 6 | Denylist enforcement | Blocks all 8 AGENTS.md denylist zones |
| 7 | Prompt sanitization | Escapes backticks, dollar signs, strips HTML, limits to 1000 chars |
| 8 | Graph context sanitization | Prevents prompt injection via node labels or file paths |
| 9 | Output filtering | Redacts secrets (API keys, JWTs, passwords) and denylist paths from output |
| 10 | Model output validation | Validates Gemini response structure before processing |
| 11 | Per-request token/cost limit | Falls back to deterministic if exceeded |
| 12 | Per-user rate limiting | Configurable requests per hour (default: 50) |
| 13 | Per-user quota | Tracks cumulative tokens/cost (default: 100K tokens, $10/month) |
| 14 | Global spend cap | Prevents runaway Gemini spending |
| 15 | Audit logging | Every request logged with user, response, tokens, cost, violations |

### Cost Estimate

| Metric | Value |
|---|---|
| Model | Gemini 3.5 Flash |
| Temperature | Not supported (model uses optimized defaults) |
| Max output tokens | 800 per request |
| Input cost | $1.50 per 1M tokens |
| Output cost | $9.00 per 1M tokens |
| Per-request cost (est.) | ~$0.003–0.01 |
| Default monthly quota | $10/user |
| Default rate limit | 50 requests/user/hour |

The cost catalog currently covers Gemini 3.6 Flash, 3.5 Flash, 3.5 Flash-Lite, 3.1 Flash-Lite, 2.5 Flash, and 2.5 Flash-Lite at the standard paid-tier rates. Historical 1.5/2.0 entries are retained only for interpreting old usage records; Gemini 2.0 Flash is not a valid new-request model after its 2026-06-01 shutdown. Verify current rates before changing the catalog.

---

*This guide covers the local development knowledge graph. The deterministic engine works without any backend. The AI-powered engine requires Supabase setup as described above.*
