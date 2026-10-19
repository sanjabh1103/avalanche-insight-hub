#!/usr/bin/env python3
"""Migrate selected storage objects between explicitly supplied projects.

This command is intentionally fail-closed.  It never reads repository ``.env``
files, has no default source project, and requires ``--apply`` before it can
upload anything.  Use it only after a fresh read-only source/target inventory
has identified missing objects.
"""
import argparse
import requests
import os

from backend.common.supabase_project_identity import CANONICAL_PROJECT_REF


def get_keys(ref: str, management_token: str) -> tuple[str, str]:
    if not management_token:
        raise RuntimeError("SUPABASE_ACCESS_TOKEN must be supplied through the environment")
    response = requests.get(
        f"https://api.supabase.com/v1/projects/{ref}/api-keys",
        headers={"Authorization": f"Bearer {management_token}"},
        timeout=30,
    )
    if response.status_code != 200:
        raise RuntimeError(f"Supabase API-key lookup failed with HTTP {response.status_code}")
    try:
        keys = response.json()
    except ValueError as exc:
        raise RuntimeError("Supabase API-key lookup returned malformed JSON") from exc
    if not isinstance(keys, list):
        raise RuntimeError("Supabase API-key lookup returned a non-list JSON value")
    try:
        service = next(k["api_key"] for k in keys if k["name"] == "service_role")
        anon = next(k["api_key"] for k in keys if k["name"] == "anon")
    except (KeyError, StopIteration) as exc:
        raise RuntimeError("Supabase API-key lookup did not return required key types") from exc
    return service, anon


def deep_list(base_url, headers, bucket, prefix="", *, page_size=100):
    """Recursively list ALL files in a bucket, handling folders and pages."""
    files = []
    offset = 0
    while True:
        r = requests.post(
            f"{base_url}/storage/v1/object/list/{bucket}",
            headers={**headers, "Content-Type": "application/json"},
            json={
                "prefix": prefix,
                "limit": page_size,
                "offset": offset,
                "search": "",
                "sortBy": {"column": "name", "order": "asc"},
            },
            timeout=30,
        )
        if r.status_code != 200:
            raise RuntimeError(
                f"Storage listing failed at prefix='{prefix}' offset={offset}: "
                f"HTTP {r.status_code} {r.text[:100]}"
            )

        try:
            items = r.json()
        except ValueError as exc:
            raise RuntimeError(
                f"Storage listing returned malformed JSON at prefix='{prefix}' offset={offset}"
            ) from exc
        if not isinstance(items, list):
            raise RuntimeError(
                f"Storage listing returned a non-list JSON value at prefix='{prefix}' offset={offset}"
            )

        for item in items:
            name = item.get("name", "")
            item_id = item.get("id")
            metadata = item.get("metadata")

            if item_id is None and metadata is None:
                # Folder — recurse with the complete prefix. Storage returns
                # folder names relative to the current prefix; dropping the
                # parent would silently undercount nested objects.
                relative_name = name.lstrip("/")
                folder_prefix = f"{prefix}{relative_name}"
                if not folder_prefix.endswith("/"):
                    folder_prefix += "/"
                sub = deep_list(base_url, headers, bucket, folder_prefix, page_size=page_size)
                files.extend(sub)
            else:
                # File — retain the full object path for download/upload.
                item = dict(item)
                item["name"] = f"{prefix}{name}" if prefix else name
                files.append(item)

        if len(items) < page_size:
            break
        offset += len(items)
    return files


def migrate_bucket(source_url, target_url, source_h, target_h, bucket, *, apply: bool):
    print(f"\n{'='*60}")
    print(f"Migrating bucket: {bucket}")
    print(f"{'='*60}")

    all_files = deep_list(source_url, source_h, bucket)
    total_size = sum(
        (f.get("metadata") or {}).get("size", 0) if isinstance(f.get("metadata"), dict) else 0
        for f in all_files
    )
    print(f"Found {len(all_files)} files, {total_size / 1024 / 1024:.1f} MB")

    migrated = 0
    failed = 0
    migrated_bytes = 0

    for f in all_files:
        name = f["name"]

        if not apply:
            continue

        # Download from the explicitly supplied source.
        r_dl = requests.get(
            f"{source_url}/storage/v1/object/{bucket}/{name}",
            headers=source_h,
            timeout=60,
        )
        if r_dl.status_code != 200:
            print(f"  ❌ DL {name}: {r_dl.status_code}")
            failed += 1
            continue

        # Upload to NEW
        ct = r_dl.headers.get("content-type", "application/octet-stream")
        r_ul = requests.post(
            f"{target_url}/storage/v1/object/{bucket}/{name}",
            headers={**target_h, "Content-Type": ct, "x-upsert": "false"},
            data=r_dl.content,
            timeout=60,
        )

        if r_ul.status_code in (200, 201):
            migrated += 1
            migrated_bytes += len(r_dl.content)
            if migrated % 20 == 0:
                print(f"  ✅ {migrated}/{len(all_files)} ({migrated_bytes / 1024 / 1024:.1f} MB)")
        else:
            print(f"  ❌ UL {name}: {r_ul.status_code} {r_ul.text[:80]}")
            failed += 1

    print(f"\n  {bucket}: {migrated} migrated, {failed} failed, {migrated_bytes / 1024 / 1024:.1f} MB")
    return migrated, failed


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-ref", required=True, help="Explicit source Supabase project ref")
    parser.add_argument(
        "--target-ref",
        default=CANONICAL_PROJECT_REF,
        help="Target Supabase project ref; defaults to the canonical restored target",
    )
    parser.add_argument(
        "--bucket",
        action="append",
        default=None,
        help="Bucket to inspect/migrate; repeat for multiple buckets",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Actually download and upload objects; without this flag the command is a dry-run inventory",
    )
    args = parser.parse_args(argv)

    if args.target_ref != CANONICAL_PROJECT_REF:
        raise SystemExit(
            f"ERROR: target ref must be canonical {CANONICAL_PROJECT_REF}; got {args.target_ref}"
        )
    if args.source_ref == args.target_ref:
        raise SystemExit("ERROR: source and target refs must differ")

    token = os.environ.get("SUPABASE_ACCESS_TOKEN", "")
    print(f"Loading API keys for source {args.source_ref} and target {args.target_ref}...")
    source_service, source_anon = get_keys(args.source_ref, token)
    target_service, target_anon = get_keys(args.target_ref, token)

    source_url = f"https://{args.source_ref}.supabase.co"
    target_url = f"https://{args.target_ref}.supabase.co"

    source_h = {"Authorization": f"Bearer {source_service}", "apikey": source_anon}
    target_h = {"Authorization": f"Bearer {target_service}", "apikey": target_anon}

    total_migrated = 0
    total_failed = 0

    for bucket in args.bucket or ["forecast-products"]:
        migrated, failed = migrate_bucket(
            source_url,
            target_url,
            source_h,
            target_h,
            bucket,
            apply=args.apply,
        )
        total_migrated += migrated
        total_failed += failed

    print(f"\n{'='*60}")
    mode = "APPLY" if args.apply else "DRY-RUN"
    print(f"{mode}: {total_migrated} migrated, {total_failed} failed")
    print(f"{'='*60}")


if __name__ == "__main__":
    main()
