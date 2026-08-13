#!/usr/bin/env bash
set -euo pipefail

# Dependency-free boundary check for the RAvaFcast candidate surface. The
# workflow runs the full Python contract suite separately after installing
# dependencies; this command verifies the declared surfaces and research-only
# boundary before that install step.

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

required_files=(
  "docs/MVP3/RAVAFCAST_FILE_ALLOWLIST.md"
  "docs/MVP3/RAvaFcast_Partner_CAPABILITY_REVIEW.md"
  "backend/common/ravafcast_contracts.py"
  "backend/common/ravafcast_runtime_gate.py"
  "backend/tests/test_ravafcast_contracts.py"
  "backend/tests/test_ravafcast_runtime_gate.py"
)

for file in "${required_files[@]}"; do
  [[ -f "$file" ]] || { echo "missing RAvaFcast surface: $file" >&2; exit 1; }
done

grep -q "production_scoring_allowed=false" docs/MVP3/RAVAFCAST_ALIGNMENT_AUDIT.md
grep -q "RAVAFCAST_PIPELINE_ENABLED=false" docs/MVP3/RAvaFcast_Partner_CAPABILITY_REVIEW.md
grep -q "Binary risk_score cannot be converted" backend/common/ravafcast_contracts.py

echo "RAvaFcast conformance boundary OK: research-only, disabled by default"
