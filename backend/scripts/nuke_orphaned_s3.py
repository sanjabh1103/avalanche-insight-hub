"""Reconcile S3 objects against the storage.objects table and delete true orphans only.

An orphan is an S3 object that exists in the bucket but has NO corresponding row
in the Supabase ``storage.objects`` table. This script never deletes objects that
are still tracked by the database, unlike the previous nuke-all approach.

Usage:
    DRY_RUN=1 python -m backend.scripts.nuke_orphaned_s3   # list orphans only
    python -m backend.scripts.nuke_orphaned_s3             # delete confirmed orphans

Environment variables:
    SUPABASE_URL                  - Supabase project URL
    SUPABASE_S3_ACCESS_KEY_ID     - S3 protocol access key
    SUPABASE_S3_ACCESS_KEY_SECRET - S3 protocol secret key
    SUPABASE_DB_PASSWORD          - Postgres password for storage.objects queries
    DRY_RUN                       - Set to '1' to list orphans without deleting
    ORPHAN_BUCKETS                - Comma-separated bucket list (optional override)
"""

from __future__ import annotations

import os
import sys
from urllib.parse import urlparse


DEFAULT_BUCKETS = [
    'forecast-products',
    'model-artifacts',
    'forecast-products-canary',
    'public-assets',
    'research-data',
    'sar-masks',
    'scientist-profiles',
]


def _get_s3_client():
    access_key_id = os.environ.get('SUPABASE_S3_ACCESS_KEY_ID', '')
    secret_access_key = os.environ.get('SUPABASE_S3_ACCESS_KEY_SECRET', '')
    if not access_key_id or not secret_access_key:
        print('::error::SUPABASE_S3_ACCESS_KEY_ID and SUPABASE_S3_ACCESS_KEY_SECRET must be set')
        return None

    try:
        import boto3
        from botocore.config import Config
    except ImportError:
        print('::error::boto3 not installed. Run: pip install boto3')
        return None

    url = os.environ.get('SUPABASE_URL', '')
    parsed = urlparse(url)
    host = parsed.hostname or ''
    if not host:
        print('::error::SUPABASE_URL not set or invalid')
        return None

    endpoint = f'https://{host}/storage/v1/s3'
    return boto3.client(
        's3',
        endpoint_url=endpoint,
        region_name='ap-south-1',
        aws_access_key_id=access_key_id,
        aws_secret_access_key=secret_access_key,
        config=Config(
            s3={'addressing_style': 'path'},
            retries={'max_attempts': 5, 'mode': 'standard'},
        ),
    )


def _list_s3_objects(s3_client, bucket_name: str) -> list[dict]:
    """List all objects in a bucket via S3 protocol, handling pagination."""
    objects: list[dict] = []
    paginator = s3_client.get_paginator('list_objects_v2')
    for page in paginator.paginate(Bucket=bucket_name):
        for obj in page.get('Contents', []):
            objects.append({
                'Key': obj['Key'],
                'Size': obj['Size'],
                'LastModified': obj['LastModified'],
            })
    return objects


def _get_db_connection():
    """Connect to the Supabase Postgres database to query storage.objects."""
    try:
        import psycopg2
    except ImportError:
        print('::error::psycopg2 not installed. Run: pip install psycopg2-binary')
        return None

    url = os.environ.get('SUPABASE_URL', '')
    parsed = urlparse(url)
    host = parsed.hostname or ''
    if not host:
        print('::error::SUPABASE_URL not set or invalid')
        return None

    project_ref = host.split('.')[0]
    db_host = os.environ.get('SUPABASE_DB_HOST') or f'db.{project_ref}.supabase.co'

    password = os.environ.get('SUPABASE_DB_PASSWORD', '')
    if not password:
        print('::error::SUPABASE_DB_PASSWORD must be set to query storage.objects')
        return None

    user = os.environ.get('SUPABASE_DB_USER', 'postgres')
    try:
        return psycopg2.connect(
            host=db_host,
            port=5432,
            dbname='postgres',
            user=user,
            password=password,
            connect_timeout=10,
            sslmode='require',
        )
    except Exception as exc:
        print(f'::error::Failed to connect to database: {exc}')
        return None


def _get_known_object_keys(conn, bucket_name: str) -> set[str]:
    """Return the set of object names (S3 keys) tracked in storage.objects for a bucket."""
    known: set[str] = set()
    try:
        with conn.cursor() as cur:
            cur.execute(
                'SELECT name FROM storage.objects WHERE bucket_id = %s',
                (bucket_name,),
            )
            for row in cur.fetchall():
                known.add(row[0])
    except Exception as exc:
        print(f'::error::Failed to query storage.objects for {bucket_name}: {exc}')
    return known


def _delete_objects(s3_client, bucket_name: str, objects: list[dict]) -> int:
    """Delete the given objects in batches of 1000 (S3 batch delete limit)."""
    deleted_count = 0
    for i in range(0, len(objects), 1000):
        batch = objects[i:i + 1000]
        response = s3_client.delete_objects(
            Bucket=bucket_name,
            Delete={'Objects': [{'Key': obj['Key']} for obj in batch]},
        )
        errors = response.get('Errors', [])
        deleted = response.get('Deleted', [])
        deleted_count += len(deleted)
        if errors:
            for err in errors:
                print(f'  ::warning::Delete error: {err.get("Key")} - {err.get("Message")}')
    return deleted_count


def main() -> int:
    dry_run = os.environ.get('DRY_RUN', '0') == '1'

    s3_client = _get_s3_client()
    if s3_client is None:
        return 1

    conn = _get_db_connection()
    if conn is None:
        return 1

    buckets_csv = os.environ.get('ORPHAN_BUCKETS', '')
    buckets = [b.strip() for b in buckets_csv.split(',') if b.strip()] if buckets_csv else DEFAULT_BUCKETS

    total_orphans = 0
    total_deleted = 0
    total_s3_objects = 0
    total_known = 0

    for bucket in buckets:
        # List S3 objects
        try:
            s3_objects = _list_s3_objects(s3_client, bucket)
        except Exception as exc:
            error_code = getattr(exc, 'response', {}).get('Error', {}).get('Code', '')
            if error_code == 'NoSuchBucket':
                print(f'Bucket {bucket}: does not exist, skipping')
                continue
            print(f'::warning::Failed to list {bucket}: {exc}')
            continue

        total_s3_objects += len(s3_objects)

        # Query storage.objects for known keys
        known_keys = _get_known_object_keys(conn, bucket)
        total_known += len(known_keys)

        # Compute orphans: S3 keys NOT in storage.objects
        s3_keys = {obj['Key'] for obj in s3_objects}
        orphan_keys = s3_keys - known_keys
        known_orphaned = s3_keys & known_keys  # should be empty (these are tracked)

        if not s3_objects:
            print(f'Bucket {bucket}: empty (0 S3 objects, {len(known_keys)} DB rows)')
            continue

        orphan_objects = [obj for obj in s3_objects if obj['Key'] in orphan_keys]
        orphan_size = sum(obj['Size'] for obj in orphan_objects)
        size_mb = orphan_size / (1024 * 1024)

        print(f'Bucket {bucket}: {len(s3_objects)} S3 objects, {len(known_keys)} DB rows, {len(orphan_keys)} orphans')

        if not orphan_objects:
            print(f'  No orphans detected — all S3 objects are tracked in storage.objects')
            continue

        print(f'  Orphan size: {size_mb:.1f} MB')
        for obj in orphan_objects[:10]:
            print(f'    ORPHAN: {obj["Key"]} ({obj["Size"]} bytes)')
        if len(orphan_objects) > 10:
            print(f'    ... and {len(orphan_objects) - 10} more orphans')

        total_orphans += len(orphan_objects)

        if dry_run:
            print(f'  DRY RUN: would delete {len(orphan_objects)} orphaned objects')
            continue

        deleted = _delete_objects(s3_client, bucket, orphan_objects)
        total_deleted += deleted
        print(f'  Deleted {deleted}/{len(orphan_objects)} orphaned objects')

    conn.close()

    print(f'\nOrphan reconciliation summary:')
    print(f'  Total S3 objects scanned: {total_s3_objects}')
    print(f'  Total DB rows matched:    {total_known}')
    print(f'  Total orphans found:      {total_orphans}')
    print(f'  Total orphans deleted:    {total_deleted}')

    if dry_run:
        print('  Mode: DRY RUN (no deletions performed)')
    else:
        print('  Mode: LIVE (orphan objects deleted)')

    return 0


if __name__ == '__main__':
    sys.exit(main())
