"""Forecast storage retention cleanup.

Deletes Supabase Storage objects for non-active forecast runs older than
FORECAST_RETENTION_DAYS (default 14). The corresponding PostgreSQL rows
are cleaned up by the pg_cron job scheduled in migration
20260627160000_forecast_retention_cleanup.sql.

This script is idempotent for already-removed objects: a 404 is treated as
success, while any other listing, measurement, or deletion failure fails the
worker closed so the database retention job cannot silently outrun it.

Deletion strategy (in order):
  1. HTTP Storage API (preferred — properly removes S3 files)
  2. S3 protocol via boto3 (fallback when HTTP API returns 402)

**IMPORTANT**: Direct SQL deletion from storage.objects is NOT used because
it creates orphaned S3 files that still count against storage quota.
See: https://supabase.com/docs/guides/storage/management/delete-objects

A successful storage quota pre-check is required before cleanup. If total
storage exceeds 80%% of the free-tier 1GB limit (800MB), emergency mode deletes
eligible non-active runs regardless of age; a missing measurement aborts.

Usage:
    python -m backend.scripts.cleanup_old_storage

Environment variables:
    SUPABASE_URL                  - Supabase project URL
    SUPABASE_SERVICE_ROLE_KEY     - Service role key for authenticated API calls
    SUPABASE_DB_PASSWORD          - Database password for SQL metadata reads
    SUPABASE_DB_HOST               - Optional database/pooler host override
    SUPABASE_DB_PORT               - Optional database/pooler port (default: 5432)
    SUPABASE_DB_USER               - Optional database user (default: postgres)
    SUPABASE_DB_NAME               - Optional database name (default: postgres)
    SUPABASE_S3_ACCESS_KEY_ID     - S3 protocol access key for deletion fallback
    SUPABASE_S3_ACCESS_KEY_SECRET - S3 protocol secret key for deletion fallback
    FORECAST_RETENTION_DAYS       - Retention period in days (default: 14)
"""

from __future__ import annotations

import os
import sys
import time
from datetime import datetime, timedelta, timezone
from urllib.parse import urlparse

import requests

from backend.common.supabase_io import _base_url, _headers, has_supabase_credentials

FORECAST_PRODUCTS_BUCKET = 'forecast-products'
STORAGE_QUOTA_BYTES = 1024 * 1024 * 1024  # 1GB free tier limit
STORAGE_QUOTA_WARN_BYTES = 600 * 1024 * 1024  # 600MB warning threshold (60%)
STORAGE_QUOTA_EMERGENCY_BYTES = 800 * 1024 * 1024  # 800MB emergency threshold (80%)


def _get_retention_days() -> int:
    raw = os.environ.get('FORECAST_RETENTION_DAYS', '14')
    try:
        days = int(raw)
        if days < 1:
            raise ValueError
        return days
    except ValueError:
        print(f'::warning::Invalid FORECAST_RETENTION_DAYS={raw}, defaulting to 14')
        return 14


def _get_db_connection():
    """Get a direct PostgreSQL connection using SUPABASE_DB_PASSWORD.

    Returns None if credentials are not available.
    """
    db_password = os.environ.get('SUPABASE_DB_PASSWORD', '')
    if not db_password:
        return None

    try:
        import psycopg2
    except ImportError:
        print('::warning::psycopg2 not installed; direct-SQL fallback unavailable')
        return None

    url = os.environ.get('SUPABASE_URL', '')
    parsed = urlparse(url)
    project_host = parsed.hostname or ''
    db_host = os.environ.get('SUPABASE_DB_HOST', '').strip()
    if not db_host:
        db_host = f'db.{project_host}' if project_host else ''
    if not db_host:
        return None

    try:
        db_port = int(os.environ.get('SUPABASE_DB_PORT', '5432'))
    except ValueError:
        print('::warning::Invalid SUPABASE_DB_PORT; using 5432')
        db_port = 5432

    try:
        conn = psycopg2.connect(
            host=db_host,
            port=db_port,
            user=os.environ.get('SUPABASE_DB_USER', 'postgres'),
            password=db_password,
            dbname=os.environ.get('SUPABASE_DB_NAME', 'postgres'),
            connect_timeout=10,
            sslmode='require',
        )
        conn.autocommit = True
        return conn
    except Exception as exc:
        print(f'::warning::Direct-SQL connection failed: {exc}')
        return None


def _sql_get_storage_usage(conn) -> dict[str, dict]:
    """Query total storage size per bucket via direct SQL.

    Returns dict: {bucket_id: {'size_bytes': int, 'object_count': int}}
    """
    with conn.cursor() as cur:
        cur.execute(
            "SELECT bucket_id, count(*) as cnt, "
            "COALESCE(sum((metadata->>'size')::bigint), 0) as total_bytes "
            "FROM storage.objects GROUP BY bucket_id"
        )
        rows = cur.fetchall()
    return {
        row[0]: {'size_bytes': int(row[2]), 'object_count': int(row[1])}
        for row in rows
    }


def _get_s3_client():
    """Get a boto3 S3 client for Supabase Storage S3 protocol.

    Returns None if S3 credentials are not available or boto3 is not installed.
    """
    access_key_id = os.environ.get('SUPABASE_S3_ACCESS_KEY_ID', '')
    secret_access_key = os.environ.get('SUPABASE_S3_ACCESS_KEY_SECRET', '')
    if not access_key_id or not secret_access_key:
        return None

    try:
        import boto3
    except ImportError:
        print('::warning::boto3 not installed; S3 protocol fallback unavailable')
        return None

    url = os.environ.get('SUPABASE_URL', '')
    parsed = urlparse(url)
    host = parsed.hostname or ''
    if not host:
        return None

    endpoint = f'https://{host}/storage/v1/s3'
    try:
        return boto3.client(
            's3',
            endpoint_url=endpoint,
            region_name='ap-south-1',
            aws_access_key_id=access_key_id,
            aws_secret_access_key=secret_access_key,
            config=__import__('botocore.config', fromlist=['Config']).Config(
                s3={'addressing_style': 'path'},
                retries={'max_attempts': 3, 'mode': 'standard'},
            ),
        )
    except Exception as exc:
        print(f'::warning::S3 client creation failed: {exc}')
        return None


def _s3_delete_object(s3_client, storage_ref: str) -> bool:
    """Delete a single object via S3 protocol. Returns True on success."""
    parts = storage_ref.split('/', 1)
    if len(parts) != 2:
        print(f'::warning::Invalid storage_ref format: {storage_ref}')
        return False

    bucket_name, object_path = parts
    try:
        s3_client.delete_object(Bucket=bucket_name, Key=object_path)
        return True
    except Exception as exc:
        # Check if it's a NoSuchKey error (already deleted — idempotent)
        error_code = getattr(exc, 'response', {}).get('Error', {}).get('Code', '')
        if error_code in ('NoSuchKey', '404'):
            return True
        print(f'::warning::S3 delete failed for {storage_ref}: {exc}')
        return False


def _sql_fetch_old_non_active_runs(conn, retention_days: int) -> list[dict]:
    """Fetch non-active forecast runs older than retention_days via direct SQL."""
    cutoff = (datetime.now(timezone.utc) - timedelta(days=retention_days))
    with conn.cursor() as cur:
        cur.execute(
            "SELECT id::text, region_key, hazard_type, created_at::text, "
            "manifest_storage_ref, runout_storage_ref, status, publication_status "
            "FROM public.forecast_runs "
            "WHERE active = false AND created_at < %s "
            "AND status <> 'ready' "
            "AND publication_status NOT IN ('validated', 'published')",
            (cutoff,),
        )
        columns = [desc[0] for desc in cur.description]
        return [dict(zip(columns, row)) for row in cur.fetchall()]


def _sql_fetch_run_hours(conn, run_id: str) -> list[dict]:
    """Fetch forecast_run_hours storage_refs for a given run via direct SQL."""
    with conn.cursor() as cur:
        cur.execute(
            "SELECT storage_ref FROM public.forecast_run_hours "
            "WHERE forecast_run_id = %s AND storage_ref IS NOT NULL",
            (run_id,),
        )
        return [{'storage_ref': row[0]} for row in cur.fetchall()]


def _sql_fetch_all_non_active_runs(conn) -> list[dict]:
    """Fetch ALL non-active forecast runs regardless of age (emergency mode)."""
    with conn.cursor() as cur:
        cur.execute(
            "SELECT id::text, region_key, hazard_type, created_at::text, "
            "manifest_storage_ref, runout_storage_ref, status, publication_status "
            "FROM public.forecast_runs "
            "WHERE active = false "
            "AND status <> 'ready' "
            "AND publication_status NOT IN ('validated', 'published')"
        )
        columns = [desc[0] for desc in cur.description]
        return [dict(zip(columns, row)) for row in cur.fetchall()]


def _is_storage_cleanup_eligible(run: dict) -> bool:
    """Keep published/ready evidence out of the Storage deletion path."""
    return (
        run.get('active') is False
        and run.get('status') != 'ready'
        and run.get('publication_status') not in {'validated', 'published'}
    )


def _check_storage_quota() -> tuple[bool, dict[str, dict]]:
    """Pre-check storage usage. Returns (emergency_mode, usage_dict)."""
    conn = _get_db_connection()
    if conn is None:
        raise RuntimeError(
            'quota pre-check requires SUPABASE_DB_PASSWORD and a database connection'
        )

    try:
        usage = _sql_get_storage_usage(conn)
        total_bytes = sum(v['size_bytes'] for v in usage.values())
        total_mb = total_bytes / (1024 * 1024)

        print(f'Storage pre-check: total usage = {total_mb:.1f} MB')
        for bucket, info in usage.items():
            print(f'  {bucket}: {info["object_count"]} objects, {info["size_bytes"] / (1024 * 1024):.1f} MB')

        if total_bytes > STORAGE_QUOTA_WARN_BYTES:
            print(f'::warning::Storage usage ({total_mb:.0f} MB) exceeds warning threshold ({STORAGE_QUOTA_WARN_BYTES / (1024 * 1024):.0f} MB)')

        emergency = total_bytes > STORAGE_QUOTA_EMERGENCY_BYTES
        if emergency:
            print(f'::warning::EMERGENCY CLEANUP triggered: storage ({total_mb:.0f} MB) exceeds emergency threshold ({STORAGE_QUOTA_EMERGENCY_BYTES / (1024 * 1024):.0f} MB)')

        conn.close()
        return emergency, usage
    except Exception as exc:
        print(f'::error::Storage quota pre-check failed: {exc}')
        try:
            conn.close()
        except Exception:
            pass
        raise RuntimeError(f'quota pre-check failed: {exc}') from exc


def _log_storage_usage_after() -> bool:
    """Log storage usage after cleanup for monitoring."""
    conn = _get_db_connection()
    if conn is None:
        print('::error::Post-cleanup storage measurement requires a database connection')
        return False

    try:
        usage = _sql_get_storage_usage(conn)
        total_bytes = sum(v['size_bytes'] for v in usage.values())
        total_mb = total_bytes / (1024 * 1024)
        print(f'\nPost-cleanup storage usage: {total_mb:.1f} MB total')
        for bucket, info in usage.items():
            print(f'  {bucket}: {info["object_count"]} objects, {info["size_bytes"] / (1024 * 1024):.1f} MB')
        if total_bytes > STORAGE_QUOTA_WARN_BYTES:
            print(f'::warning::Post-cleanup storage still above warning threshold: {total_mb:.0f} MB')
        conn.close()
        return True
    except Exception as exc:
        print(f'::error::Post-cleanup storage check failed: {exc}')
        try:
            conn.close()
        except Exception:
            pass
        return False


def _fetch_old_non_active_runs(retention_days: int) -> list[dict]:
    """Fetch forecast_runs that are non-active and older than retention_days."""
    base = _base_url()
    headers = _headers()
    cutoff = (datetime.now(timezone.utc) - timedelta(days=retention_days)).strftime('%Y-%m-%dT%H:%M:%S.%fZ')

    params = {
        'select': 'id,region_key,hazard_type,created_at,active,manifest_storage_ref,runout_storage_ref,status,publication_status',
        'active': 'eq.false',
        'created_at': f'lt.{cutoff}',
    }

    response = requests.get(
        f'{base}/rest/v1/forecast_runs',
        headers={**headers, 'Prefer': 'return=representation'},
        params=params,
        timeout=30,
    )
    response.raise_for_status()
    return [run for run in (response.json() or []) if _is_storage_cleanup_eligible(run)]


def _fetch_run_hours(run_id: str) -> list[dict]:
    """Fetch forecast_run_hours storage_refs for a given run."""
    base = _base_url()
    headers = _headers()

    response = requests.get(
        f'{base}/rest/v1/forecast_run_hours',
        headers=headers,
        params={
            'select': 'storage_ref',
            'forecast_run_id': f'eq.{run_id}',
        },
        timeout=30,
    )
    response.raise_for_status()
    return response.json() if response.json() else []


def _delete_storage_object(storage_ref: str) -> bool:
    """Delete a single object from Supabase Storage. Returns True on success."""
    base = _base_url()
    headers = _headers()

    # storage_ref is the full path: bucket/path/to/object
    # The Storage API expects: DELETE /storage/v1/object/{bucket}/{path}
    parts = storage_ref.split('/', 1)
    if len(parts) != 2:
        print(f'::warning::Invalid storage_ref format: {storage_ref}')
        return False

    bucket_name, object_path = parts
    encoded_path = requests.utils.quote(object_path, safe='/')

    response = requests.delete(
        f'{base}/storage/v1/object/{bucket_name}/{encoded_path}',
        headers=headers,
        timeout=30,
    )

    if response.status_code == 404:
        # Already deleted — idempotent success
        return True
    if response.status_code not in (200, 204):
        print(f'::warning::Failed to delete {storage_ref}: HTTP {response.status_code}')
        return False
    return True


def _collect_run_objects(run: dict, fetch_hours_fn, run_id: str) -> list[str]:
    """Collect all storage refs for a single run."""
    objects_to_delete: list[str] = []

    try:
        hours = fetch_hours_fn(run_id)
        for hour in hours:
            ref = hour.get('storage_ref')
            if ref:
                objects_to_delete.append(ref)
    except Exception as exc:
        print(f'::error::Failed to fetch run hours for {run_id}: {exc}')
        raise RuntimeError(f'run-hour storage reference listing failed for {run_id}') from exc

    runout_ref = run.get('runout_storage_ref')
    if runout_ref:
        objects_to_delete.append(runout_ref)

    manifest_ref = run.get('manifest_storage_ref')
    if manifest_ref:
        objects_to_delete.append(manifest_ref)

    return objects_to_delete


def main() -> int:
    if not has_supabase_credentials():
        print('::error::SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY must be configured')
        return 1

    retention_days = _get_retention_days()

    # --- Storage quota pre-check ---
    try:
        emergency_mode, _ = _check_storage_quota()
    except RuntimeError as exc:
        print(f'::error::{exc}')
        return 1

    if emergency_mode:
        print('EMERGENCY CLEANUP: deleting ALL non-active runs regardless of age')
    else:
        print(f'Forecast retention cleanup: deleting non-active runs older than {retention_days} days')

    # --- Try HTTP API first, fall back to SQL for reads only ---
    use_sql_reads = False
    runs: list[dict] = []
    sql_conn = None

    try:
        if emergency_mode:
            base = _base_url()
            headers = _headers()
            response = requests.get(
                f'{base}/rest/v1/forecast_runs',
                headers={**headers, 'Prefer': 'return=representation'},
                params={
                    'select': 'id,region_key,hazard_type,created_at,active,manifest_storage_ref,runout_storage_ref,status,publication_status',
                    'active': 'eq.false',
                },
                timeout=30,
            )
            response.raise_for_status()
            runs = [run for run in (response.json() or []) if _is_storage_cleanup_eligible(run)]
        else:
            runs = _fetch_old_non_active_runs(retention_days)
    except Exception as exc:
        print(f'::warning::HTTP API failed ({exc}); using SQL for reads')
        use_sql_reads = True
        sql_conn = _get_db_connection()
        if sql_conn is None:
            print('::error::SQL read fallback unavailable (SUPABASE_DB_PASSWORD not set or psycopg2 not installed)')
            return 1

        try:
            if emergency_mode:
                runs = _sql_fetch_all_non_active_runs(sql_conn)
            else:
                runs = _sql_fetch_old_non_active_runs(sql_conn, retention_days)
        except Exception as sql_exc:
            print(f'::error::SQL read also failed: {sql_exc}')
            if sql_conn:
                sql_conn.close()
            return 1

    if not runs:
        print('No non-active forecast runs found to clean up.')
        return 0 if _log_storage_usage_after() else 1

    print(f'Found {len(runs)} non-active runs to clean up.')

    # --- Prepare S3 client for deletion fallback ---
    s3_client = _get_s3_client()
    if s3_client is not None:
        print('S3 protocol fallback: available')
    else:
        print('S3 protocol fallback: not configured (set SUPABASE_S3_ACCESS_KEY_ID and SUPABASE_S3_ACCESS_KEY_SECRET)')

    total_objects_deleted = 0
    total_runs_processed = 0
    failed_deletions = 0
    use_s3_fallback = False

    for run in runs:
        run_id = run.get('id', '')
        region_key = run.get('region_key', 'unknown')
        hazard_type = run.get('hazard_type', 'avalanche')
        created_at = run.get('created_at', 'unknown')

        print(f'Processing run {run_id} (region={region_key}, hazard={hazard_type}, created={created_at})')

        try:
            if use_sql_reads and sql_conn:
                objects_to_delete = _collect_run_objects(
                    run, lambda rid: _sql_fetch_run_hours(sql_conn, rid), run_id,
                )
            else:
                objects_to_delete = _collect_run_objects(run, _fetch_run_hours, run_id)
        except Exception as exc:
            print(f'::error::Storage reference listing failed for run {run_id}: {exc}')
            if sql_conn:
                sql_conn.close()
            return 1

        for obj_ref in objects_to_delete:
            deleted = False
            if not use_s3_fallback:
                deleted = _delete_storage_object(obj_ref)
                if not deleted:
                    failed_deletions += 1
                    # HTTP API failed — try S3 fallback for this and remaining objects
                    if s3_client is not None:
                        print('::warning::HTTP Storage API deletion failed; switching to S3 protocol fallback')
                        use_s3_fallback = True
                        deleted = _s3_delete_object(s3_client, obj_ref)
                        if deleted:
                            failed_deletions -= 1
            else:
                deleted = _s3_delete_object(s3_client, obj_ref)
                if not deleted:
                    failed_deletions += 1

            if deleted:
                total_objects_deleted += 1

        total_runs_processed += 1
        time.sleep(0.1)

    if sql_conn:
        sql_conn.close()

    print(f'\nCleanup summary:')
    print(f'  Runs processed:     {total_runs_processed}')
    print(f'  Objects deleted:    {total_objects_deleted}')
    print(f'  Failed deletions:   {failed_deletions}')
    print(f'  Mode:               {"emergency" if emergency_mode else "retention"} / {"S3 fallback" if use_s3_fallback else "HTTP API"}')

    # Note: PostgreSQL row cleanup is handled by the pg_cron job
    # in migration 20260627160000_forecast_retention_cleanup.sql
    # which CASCADE-deletes forecast_run_hours and forecast_publication_events.

    # --- Post-cleanup storage monitoring ---
    if not _log_storage_usage_after():
        return 1

    if failed_deletions > 0:
        print(f'::error::{failed_deletions} storage object deletions failed. Check logs above.')
        return 1

    print('Cleanup completed successfully.')
    return 0


if __name__ == '__main__':
    sys.exit(main())
