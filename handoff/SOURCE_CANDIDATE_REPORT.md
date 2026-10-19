# Source Candidate Report

## Approved graph-only v1 source

| Field | Value |
|---|---|
| Snapshot commit | `f582d1822b3994a6d10832e66e085ab58c8304f4` |
| Parent source commit | `787758a54117900bc4cdc487e731314159e50c98` |
| Snapshot scope | 209 graph-source paths plus generator configuration |
| Non-generated dirty entries | 0 |
| Semantic status | `structural_only_semantic_unavailable` |
| Approval | `APPROVED_PUBLIC_CONTENT` |

The approved snapshot is a scoped clean source commit for the public knowledge graph. It is
not a claim that the separate main checkout is clean, and it does not publish the main checkout.
The main checkout was left untouched by this release preparation.

## Graph snapshot

| Field | Value |
|---|---|
| Graph SHA-256 | `5c1c5e28bf6a9502a5fab9fa4e9d0fedf33d569c1de0ac3bab2b9448aee24cef` |
| Manifest SHA-256 | `356f7518b1f1efcb9c4a5a03fbe663439450a66781a4c1e07001ed23ff47f47d` |
| Nodes / edges | 4,926 / 8,183 |
| Source files | 907 |
| Analyzed at | `2026-08-04T06:35:56.363104Z` |

## Public export

| Field | Value |
|---|---|
| Export status | `approved` |
| Public graph content hash | `cc26ff2f74f49fc3632cb2ba1b8504bde2e18d430e8f07348db8c018b9c3a040` |
| Public graph file SHA-256 | `df77d44e305e0877c4024e343b93da2c29ac7bf2dea9402e3ae1d0588caf3224` |
| Source graph worktree dirty | `false` |
| Owner content approval | `APPROVED_PUBLIC_CONTENT` |

## Map decision

V1 is graph-only. The map remains explicitly blocked because no rights-cleared static forecast
snapshot is available. No synthetic, fabricated, station-identifying, or unlicensed map data is
included.

## Reproduction

The export tool accepts an explicit clean source root:

```bash
python3 scripts/export_graph.py \
  --source-root /path/to/clean-scoped-source \
  --status approved \
  --owner-approval APPROVED_PUBLIC_CONTENT
python3 scripts/generate_explanations.py
```

The source and delivery hashes are recorded in
`handoff/CLEAN_SOURCE_SNAPSHOT_MANIFEST.json` and
`public/data/code-graph-manifest.json`.
