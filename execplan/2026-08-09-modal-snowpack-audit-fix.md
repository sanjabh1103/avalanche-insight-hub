# Modal/SNOWPACK/Pir Panjal Audit-Fix ExecPlan

## Purpose and observable outcome

This plan repairs the current code-level false-green risks identified in the Codex audit without claiming live Modal execution, native SNOWPACK execution, Partner approval, or Himalayan forecast skill. After the GLM-owned milestones, a fake accepted/pending Modal response cannot pass a GitHub workflow, a terminal Modal manifest cannot omit its run identity or actual runtime evidence, and a self-consistent mutation of the bundled SNOWPACK registry cannot pass the independent release gate. The customer-facing scope will be encoded as a Pir Panjal candidate shadow POC with a 48-hour target, middle elevation band, storm/new-snow and wind-slab problem scope, RF comparison baseline, Modal technical appendix, and permanently disabled official-warning eligibility.

The repository is already dirty. Existing unrelated modifications and untracked files must remain untouched. No commit, push, destructive cleanup, native binary execution, live Modal job, secret access, or Partner claim is authorized by this plan.

## Scope and non-goals

The GLM-owned scope is limited to governance records, dependency-source consistency, Modal execution contracts and route/workflow proof, the SNOWPACK R1.1 registry-root gate, and regression verification. Real Modal credentials, a deployed Modal application, an immutable artifact store, pinned MeteoIO/SNOWPACK commits, Pir Panjal forcing/geometry, initial-state payloads, independent labels, and Partner authorization are external gates and remain blocked.

The denylist files `backend/common/snowpack_physics.py`, `backend/common/verification_exit_gates.py`, `backend/common/sar_acceptance_policy.py`, `backend/common/label_governance.py`, `backend/common/risk_math.py`, `backend/train_model.py`, `supabase/config.toml`, and `backend/reproduction/` will not be modified.

## Milestones

### M1 — Governance and evidence freeze

Create one canonical machine-readable Pir Panjal POC decision record with `selected_sector=pir_panjal_nw_himalaya`, `customer_selected_poc=true`, `Partner_approved=false`, `official_warning_eligible=false`, middle elevation band, 48-hour target, storm/new-snow and wind-slab scope, native SNOWPACK as the physical engine, RF as comparison baseline, hybrid ML shadow-only, and Modal technical-shadow-only. Reconcile the release manifest, scope inventory, reconciliation document, plan, and claim ledger so the same state is described everywhere. Add named verification selectors and remove the known claim-ledger EOF whitespace.

Acceptance: one contract test finds exactly one canonical decision record; all governing documents agree on customer-selected versus Partner-approved state; no official-warning or scientific-validation claim is introduced; `git diff --check` is clean for the scoped changes.

### M2 — Modal dependency and manifest conformance

Make `backend/requirements-ci.in` the source declaration for the nearest published exact SDK `modal==0.73.83` (the requested 0.73.82 is absent from the package index), regenerate `backend/locks/ci-py312.txt`, and use the dedicated `backend/requirements-modal.in` plus `backend/locks/modal-py312.txt` for the worker image so dependencies are not installed twice. Extend the existing Modal manifest contract with run identity, compute job identity, validated call ID, input manifest ID/hash, actual Python/Modal/Torch/TorchVision/TorchAudio/CUDA versions, image identity and archive digest fields, artifact-root identity, UTC timestamp validation, clock ordering, and fail-closed validation. Reject empty, unknown, malformed, cross-run, future, naive, or non-terminal manifests. Artifact hashing must reject symlinks and paths outside the mounted artifact root.

Acceptance: malformed-manifest and path/symlink probes fail; valid terminal shadow manifests pass; no Modal declaration uses a lower bound or stale version; the image and locks identify one exact runtime.

### M3 — Modal route and workflow terminal proof

Make route semantics explicit. GPU SAR segmentation must use the declared remote GPU function and expose a result endpoint; asynchronous training/inference routes must expose accepted, pending, running, completed, failed, expired, and cancelled states distinctly. Evaluation must either use terminal polling or return a complete validated terminal manifest. GitHub Actions must submit a run ID, poll to terminal status, verify call/run identity, validate the execution manifest and artifact digest, upload both submission and terminal responses with distinct names, and fail on accepted-only, timeout, missing secret, missing artifact, or mismatch. Add static workflow tests that prohibit direct POST-only success paths for Modal jobs.

Acceptance: route tests prove the declared function/device path; fake accepted, pending, running, timeout, and mismatched-ID cases fail; a valid terminal shadow result can be uploaded.

### M4 — SNOWPACK registry-root hardening

Require exact approved registry bytes in the downloaded release bundle and compare them to a protected expected registry digest supplied outside the mutable result and snapshot files. Bind registry records to their actual manifest and payload bytes, native-output role containment, and the expected registry root. Reject duplicate roles, malformed IDs, absolute paths, traversal, symlinks, unsafe encodings, and self-consistent registry/snapshot/result mutations.

Acceptance: the existing R1.1 self-consistent mutation probe returns exit 1, a valid fixture returns 0, and the fixture-only boundary remains explicit.

### M5 — Verification and handoff

Run changed-file tests first, named Modal/SNOWPACK selectors second, dependency consistency and schedule-contract checks third, bounded full-suite attempts under the supported Python 3.12 environment, frontend checks if the workflow surface requires them, `git diff --check`, and a bounded UBS scan. Record exact commands, interpreter, exit codes, durations, skips, and warnings in a verification manifest. If a full suite does not terminate within the bounded window, report it as blocked rather than substituting historical counts.

Acceptance: all code-level gates that were actually run have terminal evidence; live Modal/native SNOWPACK/Partner gates are explicitly marked operator-blocked; residual risks are listed.

## Decision log

- Use `modal==0.73.83`: the requested `0.73.82` is not published on the current package index, while `0.73.83` is the nearest published patch after the worker image's `0.73.82` lower bound. Do not silently float versions.
- Keep the existing fallback ladder and official-warning false gate. This work hardens evidence boundaries rather than promoting compute or proxy output.
- Do not make a public UI change in the first repair block. The audit identifies a future POC evidence surface, but it is downstream of the native bundle and governance record and would expand scope before the P0 producer/consumer gates are closed.
- Treat the supplied audit as the active plan because the checked-in GLM P1 packet is narrower and cannot authorize these broader changes by itself. This is a scope exception recorded for review, not a claim that the old packet covers the work.

## Progress

- [x] Read GLM operating manual, failure modes, repository binding, and P1 packet.
- [x] Captured dirty-worktree baseline: HEAD `9571a170`, Python 3.14.5, `git diff --check` reports claim-ledger EOF blank line, codegraph index unavailable.
- [x] Confirmed dynamic workflow dry-run recommends normal PhaseLoop with no worker spawning.
- [x] M1 governance freeze — 4 contract tests pass; `git diff --check` is clean.
- [x] M2 Modal dependency and manifest conformance — 53 focused M2 tests pass; CI and dedicated Modal locks regenerate with published modal 0.73.83.
- [x] M3 route and workflow terminal proof — 8 wrapper/static tests plus route/worker tests pass; live credentials remain blocked.
- [x] M4 SNOWPACK registry-root hardening — 33 producer/consumer R1.1 tests pass and producer now requires external registry digest.
- [x] M5 verification and handoff — current broad gates pass; UBS wrapper scan has 0 critical findings; dedicated Modal-lock audit was network-blocked and live external gates remain blocked.

## Surprises and discoveries

- The prior focused selector count is not an acceptable current full-suite proof; this plan will report only commands run in this cycle.
- `requirements-ci.txt` and the worker image used `0.73.82`, but `requirements-ci.in` and `locks/ci-py312.txt` still used `0.62.25`; package resolution proved `0.73.82` is not published, so the selected exact target is `0.73.83`.
- The codegraph MCP reports that the project is not initialized; targeted file reads and repository-native tests are the fallback evidence.
- The worktree contains a large unrelated change set, so all verification must be file-scoped or explicitly classified as mixed-worktree evidence.

## Outcomes and retrospective

This section is updated only after each milestone's tests and gates complete. A milestone is not marked complete from code inspection alone.

M5 outcome: the final current-checkout supported Python 3.12 pytest run completed with 3,260 passed, 33 skipped, 15 warnings, and 27 subtests in 168.78 seconds. Frontend Vitest completed with 446 passed across 63 files; both TypeScript projects type-checked; Vite built 3,476 modules; unittest exited 0; the schedule contract and diff check passed; the CI lock audit reported no known vulnerabilities. The dedicated Modal lock audit could not complete because the network interrupted a large scikit-learn download. UBS passed the focused new wrapper scan with zero critical findings, two warnings, and sixteen informational findings. Live Modal, native SNOWPACK, durable artifact-store, forcing/geometry, customer authorization, and Partner gates remain unverified or operator-blocked.
