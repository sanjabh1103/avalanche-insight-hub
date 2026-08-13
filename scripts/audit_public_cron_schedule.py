#!/usr/bin/env python3
"""Audit the public GitHub Actions cron contract without network access.

The report deliberately separates schedule-trigger counts from runner-minute
usage.  A trigger can create a workflow run while its guarded job is skipped,
and a timeout is a ceiling rather than an observed duration.
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any

from scripts.verify_schedule_contract import extract_schedule_conditions


MONTHS_PER_YEAR = 12
DAYS_PER_YEAR = 365.2425
AVG_DAYS_PER_MONTH = DAYS_PER_YEAR / MONTHS_PER_YEAR
WEEKS_PER_YEAR = DAYS_PER_YEAR / 7
AVG_WEEKS_PER_MONTH = WEEKS_PER_YEAR / MONTHS_PER_YEAR
CRON_RE = re.compile(r"^\s*-\s*cron:\s*['\"]([^'\"]+)['\"](?:\s+#\s*(.*))?\s*$")
JOB_RE = re.compile(r"^  ([A-Za-z0-9_-]+):\s*$")
IF_RE = re.compile(r"^    if:\s*(.*)$")
TIMEOUT_RE = re.compile(r"^    timeout-minutes:\s*(\d+)\s*$")


def extract_cron_entries(text: str) -> list[dict[str, str]]:
    """Return active (non-commented) cron entries in source order."""

    entries: list[dict[str, str]] = []
    for line_number, line in enumerate(text.splitlines(), start=1):
        match = CRON_RE.match(line)
        if match:
            entries.append(
                {
                    "cron": match.group(1),
                    "comment": match.group(2) or "",
                    "line": str(line_number),
                }
            )
    return entries


def extract_job_metadata(text: str) -> dict[str, dict[str, Any]]:
    """Extract top-level job guards and timeout caps from a workflow."""

    lines = text.splitlines()
    in_jobs = False
    current_job: str | None = None
    blocks: dict[str, list[str]] = {}

    for line in lines:
        if line == "jobs:":
            in_jobs = True
            continue
        if not in_jobs:
            continue
        if line and not line.startswith(" "):
            break
        match = JOB_RE.match(line)
        if match:
            current_job = match.group(1)
            blocks[current_job] = []
            continue
        if current_job is not None:
            blocks[current_job].append(line)

    metadata: dict[str, dict[str, Any]] = {}
    for job_id, block_lines in blocks.items():
        guard = ""
        timeout_minutes: int | None = None
        for line in block_lines:
            if_match = IF_RE.match(line)
            if if_match:
                guard = if_match.group(1)
            timeout_match = TIMEOUT_RE.match(line)
            if timeout_match:
                timeout_minutes = int(timeout_match.group(1))
        metadata[job_id] = {
            "if": guard,
            "timeout_minutes": timeout_minutes,
        }
    return metadata


def classify_frequency(cron: str) -> str:
    """Classify the active schedule forms used by this repository."""

    fields = cron.split()
    if len(fields) != 5:
        return "other"
    if fields[4] != "*":
        return "weekly"
    if fields[2] == "*" and fields[3] == "*":
        return "daily"
    return "other"


def _monthly_occurrences(frequency: str) -> float:
    if frequency == "daily":
        return AVG_DAYS_PER_MONTH
    if frequency == "weekly":
        return AVG_WEEKS_PER_MONTH
    return 0.0


def build_audit_report(text: str) -> dict[str, Any]:
    """Build a machine-readable schedule and timeout-ceiling report."""

    entries = extract_cron_entries(text)
    jobs = extract_job_metadata(text)
    cron_strings = [entry["cron"] for entry in entries]
    conditions = extract_schedule_conditions(text)
    errors: list[str] = []
    if len(cron_strings) != len(set(cron_strings)):
        errors.append("active cron expressions are duplicated")

    rows: list[dict[str, Any]] = []
    for entry in entries:
        cron = entry["cron"]
        matching_jobs = [
            job_id
            for job_id, metadata in jobs.items()
            if f"github.event.schedule == '{cron}'" in metadata["if"]
            or f'github.event.schedule == "{cron}"' in metadata["if"]
        ]
        if len(matching_jobs) != 1:
            errors.append(
                f"cron {cron!r} maps to {len(matching_jobs)} job conditions"
            )
        timeout = jobs[matching_jobs[0]]["timeout_minutes"] if len(matching_jobs) == 1 else None
        frequency = classify_frequency(cron)
        occurrences = _monthly_occurrences(frequency)
        rows.append(
            {
                **entry,
                "frequency": frequency,
                "monthly_occurrences": round(occurrences, 3),
                "job_ids": matching_jobs,
                "timeout_minutes": timeout,
                "timeout_ceiling_minutes_month": round(
                    occurrences * timeout, 2
                )
                if timeout is not None
                else None,
            }
        )

    for condition in conditions:
        if condition not in cron_strings:
            errors.append(f"job condition references inactive cron {condition!r}")

    timeout_ceiling = sum(
        row["timeout_ceiling_minutes_month"] or 0.0 for row in rows
    )
    return {
        "active_trigger_count": len(entries),
        "daily_trigger_count": sum(row["frequency"] == "daily" for row in rows),
        "weekly_trigger_count": sum(row["frequency"] == "weekly" for row in rows),
        "other_trigger_count": sum(row["frequency"] == "other" for row in rows),
        "condition_count": len(conditions),
        "contract_ok": not errors,
        "errors": errors,
        "timeout_ceiling_minutes_month": round(timeout_ceiling, 2),
        "timeout_ceiling_exceeds_2000": timeout_ceiling > 2000,
        "triggers": rows,
    }


def _print_text_report(report: dict[str, Any], workflow_path: Path) -> None:
    print(f"workflow: {workflow_path}")
    print(
        "active triggers: "
        f"{report['active_trigger_count']} "
        f"(daily={report['daily_trigger_count']}, "
        f"weekly={report['weekly_trigger_count']}, "
        f"other={report['other_trigger_count']})"
    )
    print(f"job conditions: {report['condition_count']}")
    print(
        "timeout ceiling: "
        f"{report['timeout_ceiling_minutes_month']:.2f} runner-minutes/month "
        "if every scheduled job runs to its configured timeout"
    )
    for row in report["triggers"]:
        jobs = ",".join(row["job_ids"]) or "<unmapped>"
        print(
            f"{row['cron']} | {row['frequency']} | {jobs} | "
            f"timeout={row['timeout_minutes']} min | "
            f"approx={row['monthly_occurrences']}/month"
        )
    if report["errors"]:
        print("contract: FAILED")
        for error in report["errors"]:
            print(f"  - {error}")
    else:
        print("contract: OK")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "workflow",
        nargs="?",
        type=Path,
        default=Path(".github/workflows/ml_pipeline.yml"),
    )
    parser.add_argument("--json", action="store_true", dest="as_json")
    args = parser.parse_args()
    text = args.workflow.read_text(encoding="utf-8")
    report = build_audit_report(text)
    if args.as_json:
        print(json.dumps(report, indent=2, sort_keys=True))
    else:
        _print_text_report(report, args.workflow)
    return 0 if report["contract_ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
