# Himalayan Partner Source Package Checksum Guide

Decision: `partner_source_package_checksum_guide_written_pending_partner_sources`

This guide explains how partners should compute SHA-256 checksums for frozen source packages, use those checksums in CSV `source_ref` fields, and mirror them in `partner_source_manifest.json`.

| Gate | Value |
|---|---:|
| Production scoring allowed | `false` |
| Himalayan accuracy claim allowed | `false` |

## Supported Reference Formats

| Format | Use |
|---|---|
| `sha256:<64-hex-sha256-of-source-package>` | Use when the CSV source_ref points directly to a reviewed source package digest. |
| `file:raw_sources/<source-file>#sha256=<64-hex-sha256-of-source-package>` | Use when partners also provide a stable relative raw_sources path for review navigation. |

## Required Source Manifest Fields

- `source_id`
- `sha256`
- `source_owner`
- `dataset_name`
- `license_scope`
- `date_range`
- `review_status`
- `reviewer_id`
- `reviewed_at`
- `evidence_package_ref`

## Package Layout

| Path | Purpose |
|---|---|
| `<partner-package-root>/partner_source_manifest.json` | Reviewed source-governance manifest keyed by source_id and SHA-256 digest. |
| `<partner-package-root>/raw_sources/<source-file>` | Immutable source package or source export used to compute source_ref digests. |
| `<partner-package-root>/<evidence-template>.csv` | Filled evidence CSV whose source_ref values match partner_source_manifest.json. |

## Checksum Commands

### macos

```bash
shasum -a 256 raw_sources/<source-file>
```

Expected output: `<64-hex-sha256>  raw_sources/<source-file>`

### linux

```bash
sha256sum raw_sources/<source-file>
```

Expected output: `<64-hex-sha256>  raw_sources/<source-file>`

### python

```bash
/opt/homebrew/bin/python3 -c "import hashlib, pathlib; p=pathlib.Path('raw_sources/<source-file>'); print(hashlib.sha256(p.read_bytes()).hexdigest(), p)"
```

Expected output: `<64-hex-sha256> raw_sources/<source-file>`

## Workflow

- Freeze each raw source export or package before filling evidence CSV rows.
- Compute the SHA-256 digest from the frozen source file or source package.
- Add one partner_source_manifest.json source entry with sha256, owner, license, reviewer, reviewed_at, and evidence_package_ref.
- Use the same digest in each CSV source_ref that depends on that source.
- Run source-manifest validation, then full evidence validation, before scientist or claim review.

## Common Mistakes

- Hashing a file after editing it to fill CSV values.
- Using MD5, SHA-1, or a truncated digest instead of full SHA-256.
- Using an absolute private laptop path instead of a stable relative raw_sources path.
- Leaving evidence_package_ref blank in partner_source_manifest.json.
- Changing source files after checksums were recorded.
- Using a source with unreviewed, blocked, or unknown license scope.

## Standards Anchors

| Anchor | Use | URL |
|---|---|---|
| NIST FIPS 180-4 Secure Hash Standard | Treat SHA-256 as the stable source integrity reference for partner evidence packages. | https://csrc.nist.gov/pubs/fips/180-4/upd1/final |
| Python hashlib documentation | Use hashlib.sha256 for deterministic local checksum reproduction. | https://docs.python.org/3/library/hashlib.html |
| GNU coreutils sha256sum | Use sha256sum where GNU coreutils are available. | https://www.gnu.org/software/coreutils/manual/html_node/sha2-utilities.html |

## Claim Boundary

- Production scoring allowed: `false`
- Himalayan accuracy claim allowed: `false`
- Reason: This guide documents provenance mechanics only. It is not source evidence, model validation, scientist review, or production authorization.
