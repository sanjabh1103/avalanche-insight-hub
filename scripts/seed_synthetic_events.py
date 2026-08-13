#!/usr/bin/env python3
"""
Synthetic avalanche event seeder for new Supabase project.

Creates ~800 display-only events across all 8 regions using only
the standard library (no earthengine, no rasterio needed).

Usage:
  python3 scripts/seed_synthetic_events.py            # dry-run (prints JSON)
  ALLOW_SYNTHETIC_SEED=true python3 scripts/seed_synthetic_events.py --apply

Events are clearly tagged: source='synthetic', fusion_source='synthetic_seed_v1',
training_eligible=False. Live apply is opt-in only and must not be used for the
June 2026 public demo path.
"""

from __future__ import annotations

import json
import math
import os
import random
import sys
import urllib.request
import urllib.error
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
REPO_ROOT = Path(__file__).resolve().parent.parent
REGIONS_FILE = REPO_ROOT / "config" / "regions.json"

EVENTS_PER_REGION = 100        # 8 regions × 100 = 800 events total
BATCH_SIZE = 50
SEED = 42

WINTER_START = datetime(2023, 11, 1, tzinfo=timezone.utc)
WINTER_END   = datetime(2024, 4, 30, tzinfo=timezone.utc)
WINTER_DAYS  = (WINTER_END - WINTER_START).days

EVENT_TYPES  = ["dry_slab", "wet_slab", "wind_slab", "loose_wet", "loose_dry", "cornice_fall"]
TRIGGER_TYPES = ["natural", "skier", "explosive", "unknown"]
SIZE_SCALES  = ["D1", "D2", "D3", "D4"]
ASPECT_BUCKETS = ["N", "NE", "E", "SE", "S", "SW", "W", "NW"]

ANON_KEY = (
    os.environ.get("SUPABASE_ANON_KEY")
    or os.environ.get("VITE_SUPABASE_ANON_KEY")
)
SERVICE_ROLE_KEY = os.environ.get("SUPABASE_SERVICE_ROLE_KEY")
SUPABASE_URL = (
    os.environ.get("SUPABASE_URL")
    or os.environ.get("VITE_SUPABASE_URL")
)


# ---------------------------------------------------------------------------
# Load regions
# ---------------------------------------------------------------------------
def load_regions() -> list[dict]:
    if not REGIONS_FILE.exists():
        # Fallback hardcoded (matches config/regions.json)
        return [
            {"key": "colorado_rockies",   "bbox": [38.5, -107.5, 40.5, -105.5]},
            {"key": "swiss_alps",          "bbox": [46.0,   7.0,  47.5,   9.5]},
            {"key": "french_alps",         "bbox": [44.5,   5.5,  46.5,   7.5]},
            {"key": "himalayas_nepal",     "bbox": [27.0,  85.0,  29.0,  87.5]},
            {"key": "andes_patagonia",     "bbox": [-42.0, -72.0, -40.0, -70.0]},
            {"key": "cascades_wa",         "bbox": [46.5, -122.5,  48.5, -120.5]},
            {"key": "scandinavia_norway",  "bbox": [60.0,   6.0,  62.0,   8.0]},
            {"key": "japanese_alps",       "bbox": [35.5, 137.0,  37.0, 139.0]},
        ]
    raw = json.loads(REGIONS_FILE.read_text())
    # regions.json may be list or dict
    if isinstance(raw, list):
        return raw
    if isinstance(raw, dict) and "regions" in raw:
        return raw["regions"]
    # dict of key -> {bbox: ...}
    return [{"key": k, **v} for k, v in raw.items()]


# ---------------------------------------------------------------------------
# Event generation
# ---------------------------------------------------------------------------
def rand_lat_lng(bbox: list[float], rng: random.Random) -> tuple[float, float]:
    """Random point inside [lat_min, lng_min, lat_max, lng_max] bbox."""
    lat_min, lng_min, lat_max, lng_max = bbox
    return (
        round(rng.uniform(lat_min, lat_max), 5),
        round(rng.uniform(lng_min, lng_max), 5),
    )


def rand_timestamp(rng: random.Random) -> str:
    offset_days = rng.randint(0, WINTER_DAYS)
    t = WINTER_START + timedelta(days=offset_days, hours=rng.randint(6, 18))
    return t.isoformat().replace("+00:00", "Z")


def generate_events(regions: list[dict], rng: random.Random) -> list[dict]:
    events = []
    for region in regions:
        bbox = region.get("bbox") or region.get("bounding_box")
        if isinstance(bbox, dict):
            bbox = [bbox["lat_min"], bbox["lng_min"], bbox["lat_max"], bbox["lng_max"]]
        region_key = (
            region.get("key")
            or region.get("name", "unknown").lower().replace(" ", "_").replace("(", "").replace(")", "")
        )

        for _ in range(EVENTS_PER_REGION):
            lat, lng = rand_lat_lng(bbox, rng)
            severity = rng.choices([1, 2, 3, 4], weights=[1, 4, 3, 1])[0]
            confidence = round(rng.uniform(0.25, 0.65), 3)

            # Rough elevation based on typical regional ranges
            elevation_m = rng.randint(1500, 4200)

            event = {
                # Core fields
                "timestamp":             rand_timestamp(rng),
                # PostGIS geography point: use WKT string, Supabase/PostgREST accepts this
                "location":              f"POINT({lng} {lat})",
                "source":                "synthetic",
                "description":           (
                    f"Synthetic {rng.choice(EVENT_TYPES)} avalanche event seeded for "
                    f"UI display in {region_key.replace('_', ' ').title()} region."
                ),
                "severity":              severity,
                "event_type":            "unknown",
                "confidence":            confidence,
                "fusion_source":         "synthetic_seed_v1",
                # Extended columns
                "elevation_m":           elevation_m,
                "aspect_bucket":         rng.choice(ASPECT_BUCKETS),
                "trigger_type":          rng.choice(TRIGGER_TYPES),
                "size_scale":            rng.choices(SIZE_SCALES, weights=[3, 5, 3, 1])[0],
                "hazard_type":           "avalanche",
                "verification_status":   "unverified",
                "label_role":            "display_only",
                "training_eligible":     False,          # synthetic — never train on this
                "label_confidence":      confidence,
                "training_weight":       0.0,
                "features": {
                    "region_key": region_key,
                    "seed_version": "v1",
                },
                "topo_profile": {
                    "source": "synthetic",
                    "region_key": region_key,
                },
            }
            events.append(event)

    rng.shuffle(events)
    return events


# ---------------------------------------------------------------------------
# Supabase REST upsert
# ---------------------------------------------------------------------------
def post_batch(rows: list[dict]) -> dict:
    url = f"{SUPABASE_URL}/rest/v1/avalanche_events?on_conflict=id"
    body = json.dumps(rows).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=body,
        headers={
            "apikey":         SERVICE_ROLE_KEY,
            "Authorization":  f"Bearer {SERVICE_ROLE_KEY}",
            "Content-Type":   "application/json",
            "Prefer":         "resolution=merge-duplicates,return=minimal",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return {"status": resp.status, "ok": True}
    except urllib.error.HTTPError as exc:
        body_text = exc.read().decode("utf-8", errors="replace")[:300]
        return {"status": exc.code, "ok": False, "error": body_text}


def count_events() -> int | None:
    url = f"{SUPABASE_URL}/rest/v1/avalanche_events?select=id&limit=1"
    req = urllib.request.Request(
        url,
        headers={
            "apikey":         ANON_KEY,
            "Authorization":  f"Bearer {ANON_KEY}",
            "Prefer":         "count=exact",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            cr = resp.headers.get("content-range", "")
            # Format: 0-0/1234
            if "/" in cr:
                return int(cr.split("/")[-1])
    except Exception:
        pass
    return None


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main() -> None:
    apply = "--apply" in sys.argv
    rng = random.Random(SEED)

    print("Loading regions...")
    regions = load_regions()
    print(f"  {len(regions)} regions found: {[r.get('key') or r.get('name','?') for r in regions]}")

    print(f"Generating {EVENTS_PER_REGION} events × {len(regions)} regions = {EVENTS_PER_REGION * len(regions)} total...")
    events = generate_events(regions, rng)

    if not apply:
        print("\n── DRY RUN ─────────────────────────────────")
        print(f"  Would insert {len(events)} events")
        print("  Sample event:")
        sample = {k: v for k, v in list(events[0].items())[:8]}
        print(json.dumps(sample, indent=4))
        print("\nRe-run with --apply to insert.")
        return

    if os.environ.get("ALLOW_SYNTHETIC_SEED") != "true":
        raise SystemExit("Synthetic apply is disabled. Set ALLOW_SYNTHETIC_SEED=true only for private test fixtures.")
    if not SUPABASE_URL:
        raise SystemExit("SUPABASE_URL is required for --apply")
    if not SERVICE_ROLE_KEY:
        raise SystemExit("SUPABASE_SERVICE_ROLE_KEY is required for --apply")
    if not ANON_KEY:
        raise SystemExit("SUPABASE_ANON_KEY is required for --apply")

    print(f"\nInserting {len(events)} events in batches of {BATCH_SIZE}...")
    before = count_events()
    print(f"  Events before: {before}")

    inserted = 0
    errors = 0
    for i in range(0, len(events), BATCH_SIZE):
        batch = events[i : i + BATCH_SIZE]
        result = post_batch(batch)
        if result["ok"]:
            inserted += len(batch)
            print(f"  ✅ Batch {i//BATCH_SIZE + 1}: inserted {len(batch)} (total so far: {inserted})")
        else:
            errors += len(batch)
            print(f"  ❌ Batch {i//BATCH_SIZE + 1}: HTTP {result['status']} — {result.get('error', '')[:120]}")
            if errors > 100:
                print("  Too many errors, stopping.")
                break

    after = count_events()
    print(f"\n✅ Done: {inserted} inserted, {errors} errors")
    print(f"  Events after: {after}")
    print(json.dumps({
        "inserted": inserted,
        "errors": errors,
        "events_before": before,
        "events_after": after,
        "dry_run": False,
    }, indent=2))


if __name__ == "__main__":
    main()
