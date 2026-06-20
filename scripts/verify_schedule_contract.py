#!/usr/bin/env python3
"""Verify that every scheduled cron in a workflow has exactly one job condition.

This prevents the regression where cron strings are staggered but job `if` guards
still compare against the old minute strings, causing all scheduled jobs to skip.
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
    return re.findall(r"github\.event\.schedule\s*==\s*'([^']+)'", text)


def main() -> int:
    workflow_path = Path(".github/workflows/ml_pipeline.yml")
    text = workflow_path.read_text(encoding="utf-8")
    workflow = load_workflow(workflow_path)

    cron_triggers = set(workflow.get("on", {}).get("schedule", []))
    cron_strings = {entry["cron"] for entry in cron_triggers if isinstance(entry, dict)}

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

    print(f"schedule contract OK: {len(cron_strings)} cron triggers, {len(conditions)} job conditions")
    return 0


if __name__ == "__main__":
    sys.exit(main())
