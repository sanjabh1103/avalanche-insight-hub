#!/usr/bin/env python3
"""Create a redacted, read-only inventory of the restored Supabase target.

The command reads credentials only from the process environment.  It never
loads repository ``.env`` files, prints credentials, or writes to Supabase.
Use it for a current-state inventory before any source-to-target repair.

Example::

    SUPABASE_URL=https://<project>.supabase.co \
    SUPABASE_SERVICE_ROLE_KEY=<redacted> \
    python -m backend.scripts.verify_supabase_restored_state \
      --output /tmp/restored-state.json
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from backend.common.supabase_project_identity import (
    SupabaseProjectIdentityError,
    assert_canonical_project_url,
)


TABLES = (
    "forecast_runs",
    "forecast_grids",
    "forecast_run_hours",
    "forecast_publication_events",
    "avalanche_events",
    "compute_jobs",
    "snow_cover_snapshots",
    "field_reports",
    "system_config",
    "evaluation_runs",
    "calibration_profiles",
    "calibration_reports",
    "feature_completeness_log",
    "hindcast_runs",
    "label_matching_policies",
    "label_snapshots",
    "threshold_profiles",
    "forecast_shap_cache",
    "sar_detection_artifacts",
    "verification_review_queue",
    "verification_observations",
    "verification_baselines",
    "scientist_validation_cases",
    "reviewed_shadow_training_candidates",
    "scientist_validation_reviews",
    "scientist_validation_actions",
    "scientist_daily_verifications",
    "model_status",
    "snowpack_runs",
)

BUCKETS = (
    "forecast-products",
    "model-artifacts",
    "sar-masks",
    "knowledge-graph-snapshots",
    "poc-artifacts",
)


class InventoryError(RuntimeError):
    """Raised when a read-only inventory cannot be completed safely."""


def _request_json(
    *,
    url: str,
    key: str,
    method: str = "GET",
    body: bytes | None = None,
    extra_headers: dict[str, str] | None = None,
) -> tuple[int, dict[str, str], Any]:
    headers = {
        "apikey": key,
        "Authorization": f"Bearer {key}",
        "Accept": "application/json",
    }
    if body is not None:
        headers["Content-Type"] = "application/json"
    if extra_headers:
        headers.update(extra_headers)
    request = Request(url, method=method, data=body, headers=headers)
    try:
        with urlopen(request, timeout=30) as response:
            raw = response.read()
            try:
                payload = json.loads(raw.decode("utf-8")) if raw else None
            except (UnicodeDecodeError, json.JSONDecodeError) as exc:
                raise InventoryError(f"invalid JSON response from {url}") from exc
            return response.status, dict(response.headers.items()), payload
    except HTTPError as exc:
        # Do not include the response body: it can contain sensitive details.
        raise InventoryError(f"Supabase request failed with HTTP {exc.code}: {url}") from exc
    except (OSError, URLError) as exc:
        raise InventoryError(f"Supabase request failed: {url}") from exc


def _count_from_content_range(headers: dict[str, str]) -> int:
    content_range = next(
        (value for name, value in headers.items() if name.lower() == "content-range"),
        "",
    )
    if "/" not in content_range:
        raise InventoryError("count response did not include Content-Range")
    total = content_range.rsplit("/", 1)[1]
    if total == "*" or not total.isdigit():
        raise InventoryError("count response contained an invalid Content-Range")
    return int(total)


def _table_count(base_url: str, key: str, table: str) -> int:
    query = urlencode({"select": "id", "limit": "1"})
    status, headers, _ = _request_json(
        url=f"{base_url}/rest/v1/{table}?{query}",
        key=key,
        extra_headers={"Range": "0-0", "Prefer": "count=exact"},
    )
    if status not in (200, 206):
        raise InventoryError(f"unexpected status {status} for table {table}")
    return _count_from_content_range(headers)


def _forecast_runs(base_url: str, key: str) -> list[dict[str, Any]]:
    query = urlencode({
        "select": "id,region_key,manifest_storage_ref,runout_storage_ref",
        "limit": "1000",
    })
    status, _, payload = _request_json(
        url=f"{base_url}/rest/v1/forecast_runs?{query}",
        key=key,
    )
    if status != 200 or not isinstance(payload, list):
        raise InventoryError("forecast_runs response was not a JSON list")
    rows: list[dict[str, Any]] = []
    for row in payload:
        if not isinstance(row, dict):
            raise InventoryError("forecast_runs contained a non-object row")
        rows.append({
            "id": row.get("id"),
            "region_key": row.get("region_key"),
            "manifest_storage_ref": row.get("manifest_storage_ref"),
            "runout_storage_ref": row.get("runout_storage_ref"),
        })
    return rows


def _forecast_run_hours(base_url: str, key: str) -> dict[str, list[str]]:
    """Read every hourly Storage reference with bounded pagination."""
    by_run: dict[str, list[str]] = {}
    offset = 0
    page_size = 1000
    while True:
        query = urlencode({
            "select": "forecast_run_id,storage_ref",
            "limit": str(page_size),
            "offset": str(offset),
        })
        status, _, payload = _request_json(
            url=f"{base_url}/rest/v1/forecast_run_hours?{query}",
            key=key,
        )
        if status != 200 or not isinstance(payload, list):
            raise InventoryError("forecast_run_hours response was not a JSON list")
        for row in payload:
            if not isinstance(row, dict):
                raise InventoryError("forecast_run_hours contained a non-object row")
            run_id = row.get("forecast_run_id")
            storage_ref = row.get("storage_ref")
            if not isinstance(run_id, str) or not run_id:
                raise InventoryError("forecast_run_hours contained an invalid run id")
            if not isinstance(storage_ref, str) or not storage_ref:
                raise InventoryError("forecast_run_hours contained an invalid storage reference")
            by_run.setdefault(run_id, []).append(storage_ref)
        if len(payload) < page_size:
            break
        offset += page_size
    return by_run


def _list_bucket(base_url: str, key: str, bucket: str) -> list[str]:
    files: list[str] = []
    pending = [""]
    seen_prefixes: set[str] = set()
    while pending:
        prefix = pending.pop()
        if prefix in seen_prefixes:
            raise InventoryError(f"storage prefix loop detected in {bucket!r}")
        seen_prefixes.add(prefix)
        body = json.dumps({"prefix": prefix, "limit": 1000, "offset": 0, "search": ""}).encode()
        status, _, payload = _request_json(
            url=f"{base_url}/storage/v1/object/list/{bucket}",
            key=key,
            method="POST",
            body=body,
        )
        if status != 200 or not isinstance(payload, list):
            raise InventoryError(f"storage listing for {bucket!r} was not a JSON list")
        for item in payload:
            if not isinstance(item, dict):
                raise InventoryError(f"storage listing for {bucket!r} contained a non-object")
            name = item.get("name")
            if not isinstance(name, str) or not name:
                raise InventoryError(f"storage listing for {bucket!r} contained an invalid name")
            item_id = item.get("id")
            metadata = item.get("metadata")
            if item_id is None and metadata is None:
                relative_name = name.lstrip("/")
                child = f"{prefix}{relative_name}"
                if not child.endswith("/"):
                    child = f"{child}/"
                if not child.startswith(prefix) or child == prefix:
                    raise InventoryError(f"storage listing escaped prefix {prefix!r}")
                pending.append(child)
            else:
                path = f"{prefix}{name}" if prefix else name
                files.append(path)
    return sorted(set(files))


def _auth_inventory(base_url: str, key: str) -> dict[str, Any]:
    status, _, payload = _request_json(
        url=f"{base_url}/auth/v1/admin/users?page=1&per_page=1000",
        key=key,
    )
    if status != 200 or not isinstance(payload, dict):
        raise InventoryError("Auth Admin users response was not a JSON object")
    users = payload.get("users")
    if not isinstance(users, list):
        raise InventoryError("Auth Admin users response lacked a users list")
    identity_count = 0
    for user in users:
        if isinstance(user, dict) and isinstance(user.get("identities"), list):
            identity_count += len(user["identities"])
    return {"user_count": len(users), "identity_count": identity_count}


def _capacity_snapshot(base_url: str, key: str) -> dict[str, Any]:
    """Read the service-role-only database and Storage capacity projection."""
    status, _, payload = _request_json(
        url=f"{base_url.rstrip('/')}/rest/v1/rpc/get_capacity_snapshot",
        key=key,
        method="POST",
        body=b"{}",
    )
    if status != 200 or not isinstance(payload, list) or len(payload) != 1:
        raise InventoryError("capacity snapshot RPC did not return exactly one row")
    row = payload[0]
    if not isinstance(row, dict):
        raise InventoryError("capacity snapshot RPC returned a non-object row")
    required = {
        "database_bytes",
        "database_limit_bytes",
        "storage_bytes",
        "storage_limit_bytes",
        "database_status",
        "storage_status",
    }
    if not required.issubset(row):
        missing = ", ".join(sorted(required - set(row)))
        raise InventoryError(f"capacity snapshot RPC omitted fields: {missing}")
    return {field: row[field] for field in sorted(required)}


def _storage_reference_audit(
    runs: list[dict[str, Any]],
    bucket_files: dict[str, list[str]],
) -> dict[str, Any]:
    known = {bucket: set(files) for bucket, files in bucket_files.items()}
    checked = 0
    missing: list[dict[str, Any]] = []
    hourly_checked = 0
    hourly_missing = 0
    hourly_missing_samples: list[dict[str, Any]] = []
    for row in runs:
        for field in ("manifest_storage_ref", "runout_storage_ref"):
            reference = row.get(field)
            if reference in (None, ""):
                continue
            if not isinstance(reference, str) or "/" not in reference:
                missing.append({"run_id": row.get("id"), "field": field, "reference": reference})
                continue
            bucket, object_path = reference.split("/", 1)
            checked += 1
            if object_path not in known.get(bucket, set()):
                missing.append({"run_id": row.get("id"), "field": field, "reference": reference})
        hourly_references = row.get("hourly_storage_refs", [])
        if not isinstance(hourly_references, list):
            hourly_references = []
            hourly_missing += 1
            hourly_missing_samples.append({
                "run_id": row.get("id"),
                "field": "forecast_run_hours",
                "reference": "invalid hourly reference collection",
            })
        for reference in hourly_references:
            hourly_checked += 1
            if not isinstance(reference, str) or "/" not in reference:
                hourly_missing += 1
                if len(hourly_missing_samples) < 25:
                    hourly_missing_samples.append({
                        "run_id": row.get("id"),
                        "field": "forecast_run_hours",
                        "reference": reference,
                    })
                continue
            bucket, object_path = reference.split("/", 1)
            if object_path not in known.get(bucket, set()):
                hourly_missing += 1
                if len(hourly_missing_samples) < 25:
                    hourly_missing_samples.append({
                        "run_id": row.get("id"),
                        "field": "forecast_run_hours",
                        "reference": reference,
                    })
    return {
        "checked_reference_count": checked,
        "missing_reference_count": len(missing),
        "missing_references": missing,
        "hourly_checked_reference_count": hourly_checked,
        "hourly_missing_reference_count": hourly_missing,
        "hourly_missing_reference_samples": hourly_missing_samples,
    }


def build_inventory(*, base_url: str, key: str) -> dict[str, Any]:
    base_url = base_url.rstrip("/")
    assert_canonical_project_url(base_url)
    table_counts = {table: _table_count(base_url, key, table) for table in TABLES}
    runs = _forecast_runs(base_url, key)
    hourly_refs = _forecast_run_hours(base_url, key)
    for row in runs:
        row["hourly_storage_refs"] = hourly_refs.get(str(row["id"]), [])
    bucket_files = {bucket: _list_bucket(base_url, key, bucket) for bucket in BUCKETS}
    return {
        "schema_version": "restored_supabase_state_inventory_v2",
        "captured_at": datetime.now(timezone.utc).isoformat(),
        "project_ref": base_url.removeprefix("https://").removesuffix(".supabase.co"),
        "supabase_url": base_url,
        "evidence_class": "read_only_target_inventory",
        "tables": table_counts,
        "storage": {bucket: {"object_count": len(files)} for bucket, files in bucket_files.items()},
        "capacity": _capacity_snapshot(base_url, key),
        "auth": _auth_inventory(base_url, key),
        "forecast_storage_reference_audit": _storage_reference_audit(runs, bucket_files),
        "poc_state": {
            "snowpack_runs": table_counts["snowpack_runs"],
            "poc_artifacts": len(bucket_files["poc-artifacts"]),
        },
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", default=os.environ.get("SUPABASE_URL", ""))
    parser.add_argument(
        "--key-env",
        default="SUPABASE_SERVICE_ROLE_KEY",
        help="Environment variable containing the service-role key; value is never printed",
    )
    parser.add_argument("--output", type=Path, help="Optional JSON output path")
    args = parser.parse_args(argv)
    key = os.environ.get(args.key_env, "")
    if not args.url:
        print("ERROR: --url or SUPABASE_URL is required", file=sys.stderr)
        return 2
    if not key:
        print(f"ERROR: environment variable {args.key_env} is required", file=sys.stderr)
        return 2
    try:
        inventory = build_inventory(base_url=args.url, key=key)
    except (InventoryError, SupabaseProjectIdentityError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    rendered = json.dumps(inventory, indent=2, sort_keys=True)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered + "\n", encoding="utf-8")
    print(rendered)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
