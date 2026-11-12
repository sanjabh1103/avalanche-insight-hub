#!/usr/bin/env python3
"""Verify that every GitHub Actions schedule has exactly one job condition.

This prevents the regression where cron strings are staggered but job `if` guards
still compare against the old minute strings, causing all scheduled jobs to skip.

This checks the GitHub Actions plane only. Supabase ``pg_cron`` jobs are a
separate control plane and must be verified from the linked database migration
and ``cron.job`` inventory; their counts must not be compared directly.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

import yaml


def load_workflow(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as handle:
        return yaml.safe_load(handle)


def extract_schedule_conditions(text: str) -> list[str]:
    """Return all github.event.schedule string literals found in the file."""
    active_text = "\n".join(
        line for line in text.splitlines()
        if not line.lstrip().startswith('#')
    )
    return re.findall(r"github\.event\.schedule\s*==\s*'([^']+)'", active_text)


def extract_cron_triggers(text: str) -> set[str]:
    """Return active cron strings, ignoring commented YAML lines."""
    active_text = "\n".join(
        line for line in text.splitlines()
        if not line.lstrip().startswith('#')
    )
    return set(re.findall(r"^\s*-\s*cron:\s*['\"]([^'\"]+)['\"]", active_text, re.MULTILINE))


def main() -> int:
    workflow_path = Path(".github/workflows/ml_pipeline.yml")
    text = workflow_path.read_text(encoding="utf-8")
    workflow = load_workflow(workflow_path)

    # YAML 1.1 parses bare 'on' as boolean True, so check both keys.
    on_key = "on" if "on" in workflow else (True if True in workflow else None)
    if on_key is None:
        print("No 'on' key found in workflow")
        return 1
    cron_triggers = workflow.get(on_key, {}).get("schedule", [])
    cron_strings = {entry["cron"] for entry in cron_triggers if isinstance(entry, dict)}
    schedule_source = workflow_path
    if not cron_strings:
        template_path = workflow_path.parents[2] / "config" / "public_cron_schedule.yml"
        if template_path.is_file():
            cron_strings = extract_cron_triggers(template_path.read_text(encoding="utf-8"))
            schedule_source = template_path

    conditions = extract_schedule_conditions(text)

    errors = []

    for cron in cron_strings:
        matches = conditions.count(cron)
        if matches == 0:
            errors.append(f"CRON '{cron}' has no matching job condition")
        elif matches > 1:
            errors.append(f"CRON '{cron}' is matched by {matches} job conditions (expected 1)")

    for cond in conditions:
        if cond not in cron_strings:
            errors.append(f"Job condition references '{cond}' but no such cron trigger exists")

    if errors:
        print("schedule contract FAILED:")
        for error in errors:
            print(f"  - {error}")
        return 1

    print(
        f"schedule contract OK: {len(cron_strings)} cron triggers, "
        f"{len(conditions)} job conditions (source: {schedule_source})"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
