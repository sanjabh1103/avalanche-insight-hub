#!/usr/bin/env bash
set -euo pipefail

# Operator-controlled Phase 2 refresh. This script never runs from a browser,
# never enables Understand auto-update, and produces a structural-only snapshot
# when the external semantic orchestration is unavailable.

ROOT="$(git rev-parse --show-toplevel)"
PLUGIN_ROOT="${UNDERSTAND_PLUGIN_ROOT:-$HOME/.understand-anything/repo/understand-anything-plugin}"
SKILL_DIR="$PLUGIN_ROOT/skills/understand"
INTERMEDIATE="$ROOT/.understand-anything/intermediate"
LOCKFILE="$INTERMEDIATE/.refresh-lock"

# CRITICAL: Lock file to prevent concurrent refresh
mkdir -p "$INTERMEDIATE"
if [[ -f "$LOCKFILE" ]]; then
  LOCK_AGE=$(( $(date +%s) - $(stat -f %m "$LOCKFILE" 2>/dev/null || stat -c %Y "$LOCKFILE" 2>/dev/null || echo 0) ))
  if [[ "$LOCK_AGE" -gt 3600 ]]; then
    echo "WARNING: Stale lock file found (age: ${LOCK_AGE}s). Removing." >&2
    rm -f "$LOCKFILE"
  else
    echo "ERROR: Refresh already in progress. Lock file: $LOCKFILE (age: ${LOCK_AGE}s)" >&2
    exit 1
  fi
fi
echo $$ > "$LOCKFILE"
trap 'rm -f "$LOCKFILE"' EXIT INT TERM

for required in \
  "$SKILL_DIR/scan-project.mjs" \
  "$SKILL_DIR/extract-import-map.mjs" \
  "$SKILL_DIR/compute-batches.mjs" \
  "$SKILL_DIR/extract-structure.mjs" \
  "$ROOT/scripts/build_structural_knowledge_snapshot.py"; do
  if [[ ! -f "$required" ]]; then
    echo "Required Phase 2 tool is missing: $required" >&2
    exit 1
  fi
done

mkdir -p "$INTERMEDIATE"

printf '[Phase 2/7] Deterministic scan...\n'
node "$SKILL_DIR/scan-project.mjs" "$ROOT" "$INTERMEDIATE/scan-result.json"

python3 - "$ROOT" "$INTERMEDIATE" <<'PY'
import json
import sys
from pathlib import Path
root = Path(sys.argv[1])
intermediate = Path(sys.argv[2])
scan = json.loads((intermediate / 'scan-result.json').read_text())
scan['projectRoot'] = str(root)
(intermediate / 'import-map-input.json').write_text(json.dumps(scan))
PY

printf '[Phase 2/7] Import map...\n'
node "$SKILL_DIR/extract-import-map.mjs" \
  "$INTERMEDIATE/import-map-input.json" \
  "$INTERMEDIATE/import-map.json"

printf '[Phase 2/7] Community batches...\n'
node "$SKILL_DIR/compute-batches.mjs" "$ROOT"

python3 - "$ROOT" "$INTERMEDIATE" <<'PY'
import json
import sys
from pathlib import Path
root = Path(sys.argv[1])
intermediate = Path(sys.argv[2])
batches = json.loads((intermediate / 'batches.json').read_text())['batches']
imports = json.loads((intermediate / 'import-map.json').read_text())['importMap']
for batch in batches:
    index = int(batch['batchIndex'])
    payload = {
        'projectRoot': str(root),
        'batchFiles': batch['files'],
        'batchImportData': {file['path']: imports.get(file['path'], []) for file in batch['files']},
    }
    (intermediate / f'batch-input-{index:03d}.json').write_text(json.dumps(payload))
PY

printf '[Phase 2/7] Tree-sitter structure...\n'
for input in "$INTERMEDIATE"/batch-input-*.json; do
  index="${input##*/batch-input-}"
  index="${index%.json}"
  node "$SKILL_DIR/extract-structure.mjs" "$input" "$INTERMEDIATE/structure-batch-$index.json"
done

python3 - "$INTERMEDIATE" <<'PY'
import json
import shutil
import sys
from pathlib import Path
intermediate = Path(sys.argv[1])
for structure in sorted(intermediate.glob('structure-batch-*.json')):
    index = structure.stem.rsplit('-', 1)[-1]
    payload = json.loads(structure.read_text())
    (intermediate / f'batch-{index}.json').write_text(json.dumps({
        'nodes': [
            {
                'id': f"file:{row['path']}",
                'type': 'file',
                'name': Path(row['path']).name,
                'filePath': row['path'],
            }
            for row in payload.get('results', [])
        ],
        'edges': [],
    }))
PY

printf '[Phase 7/7] Build structural snapshot and manifest...\n'
python3 "$ROOT/scripts/build_structural_knowledge_snapshot.py" --root "$ROOT" --intermediate "$INTERMEDIATE"
printf 'Phase 2 structural refresh complete. Semantic Understand refresh remains separate and must not be inferred from this artifact.\n'
