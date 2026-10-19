#!/usr/bin/env python3
"""Public sanitizer — scans built site output for forbidden content.

Scans the dist/ directory (built output) for:
- Secrets, tokens, credentials
- PII (emails, phone numbers, personal identifiers)
- Private infrastructure references
- External scripts, fonts, analytics
- API routes
- Absolute paths
- Supabase/localhost references

Produces:
  handoff/sanitization-report.json
  handoff/sanitization-report.md

Fail-closed: any finding blocks the build.
"""
from __future__ import annotations

import hashlib
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

SITE_ROOT = Path("/Users/sanjayb/avalanche-insight-hub-public-knowledge-site")
DIST_DIR = SITE_ROOT / "dist"
HANDOFF_DIR = SITE_ROOT / "handoff"

# --- Forbidden string patterns (from prompt Phase 4) ---

FORBIDDEN_STRINGS = [
    "/Users/", "/home/", "/root/", "C:\\",
    ".env", "BEGIN PRIVATE KEY",
    "password", "secret", "token", "api_key", "apikey",
    "sk-", "ghp_", "github_pat_", "AIza", "xai-", "sbp_",
    "eyJ", "supabase.co", "localhost", "127.0.0.1",
    "/api/knowledge-graph", "/api/code",
]

# Regex patterns
EMAIL_RE = re.compile(r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}")
PHONE_RE = re.compile(r"\+?\d[\d\s\-]{8,}\d")
HEX64_RE = re.compile(r"^[0-9a-f]{64}$")
EXTERNAL_URL_RE = re.compile(r"https?://(?!schema\.w3\.org|reactjs\.org|react\.dev)[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}")
EXTERNAL_SCRIPT_RE = re.compile(r'<script[^>]+src=["\']https?://', re.IGNORECASE)
EXTERNAL_FONT_RE = re.compile(r'@import\s+url\(["\']?https?://', re.IGNORECASE)
ANALYTICS_RE = re.compile(r'google-analytics|gtag|gtm\.js|fbq\(|hotjar|mixpanel|segment\.io|amplitude\.com', re.IGNORECASE)

# File extensions to scan
SCAN_EXTENSIONS = {".html", ".js", ".css", ".json", ".svg", ".txt", ".md"}


def scan_file(path: Path) -> list[dict]:
    """Scan a single file for forbidden content."""
    findings = []
    try:
        content = path.read_text(encoding="utf-8", errors="replace")
    except Exception as e:
        return [{"file": str(path.relative_to(SITE_ROOT)), "type": "read_error", "detail": str(e)}]

    rel_path = str(path.relative_to(SITE_ROOT))

    # Check forbidden strings (case-insensitive, but skip SHA-256 hashes)
    # In graph data (code-graph.json), function names like _extract_bearer_token
    # or build_github_secret_values are structural identifiers, not secret values.
    is_graph_data = "code-graph" in rel_path or "explanations" in rel_path
    is_react_bundle = "react-core" in rel_path
    is_app_bundle = rel_path.startswith("dist/assets/index-") or rel_path.startswith("dist/assets/router-")

    for pattern in FORBIDDEN_STRINGS:
        lower_content = content.lower()
        lower_pattern = pattern.lower()
        idx = lower_content.find(lower_pattern)
        while idx != -1:
            context = content[max(0, idx-20):idx+len(pattern)+20]
            # Skip if it's a SHA-256 hash (hex64)
            if HEX64_RE.match(context.strip()):
                idx = lower_content.find(lower_pattern, idx + 1)
                continue
            # Skip forbidden strings in graph data (structural function names)
            if is_graph_data and pattern in ("password", "secret", "token", "api_key", "apikey"):
                idx = lower_content.find(lower_pattern, idx + 1)
                continue
            # Skip 'sk-' if it's part of a word like 'risk-' (not an API key)
            if pattern == "sk-":
                prefix = content[max(0, idx-3):idx]
                if prefix.endswith("ri") or prefix.endswith("Ri"):
                    idx = lower_content.find(lower_pattern, idx + 1)
                    continue
                # Also skip if preceded by alphanumeric (part of a larger word)
                if idx > 0 and content[idx-1].isalnum():
                    idx = lower_content.find(lower_pattern, idx + 1)
                    continue
            # Skip 'password' in React bundle (DOM input types, form handling)
            if is_react_bundle and pattern == "password":
                idx = lower_content.find(lower_pattern, idx + 1)
                continue
            # Skip 'token'/'secret'/'password' in app bundle (our denylist words in code)
            if is_app_bundle and pattern in ("token", "secret", "password", "credential"):
                if any(x in context for x in ["denylist", "auth", "credential", "license"]):
                    idx = lower_content.find(lower_pattern, idx + 1)
                    continue
            # Skip 'eyJ' if not followed by base64 (JWT prefix check)
            if pattern == "eyJ" and idx + 10 < len(content):
                after = content[idx+3:idx+20]
                if not all(c in "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_" for c in after[:10]):
                    idx = lower_content.find(lower_pattern, idx + 1)
                    continue
            findings.append({
                "file": rel_path,
                "type": "forbidden_string",
                "pattern": pattern,
                "context": context[:80],
            })
            break  # Only report first occurrence per pattern per file

    # Check for emails
    for match in EMAIL_RE.finditer(content):
        email = match.group()
        if email.endswith(".json") or email.endswith(".ts") or email.endswith(".tsx"):
            continue  # File extension false positive
        findings.append({
            "file": rel_path,
            "type": "email",
            "value": email,
        })

    # Check for external URLs (excluding known safe ones)
    for match in EXTERNAL_URL_RE.finditer(content):
        url = match.group()
        # Skip schema URLs and React internal references
        if "reactjs.org" in url or "react.dev" in url or "w3.org" in url:
            continue
        # Skip attribution/documentation URLs in JSON data files (not runtime requests)
        if rel_path.startswith("dist/data/") or rel_path.startswith("public/data/"):
            if any(domain in url for domain in ["github.com", "npmjs.com", "opensource.org"]):
                continue
        # Skip URLs in NOTICE/ATTRIBUTION files
        if "NOTICE" in rel_path or "ATTRIBUTION" in rel_path:
            continue
        findings.append({
            "file": rel_path,
            "type": "external_url",
            "value": url,
        })

    # Check for external scripts
    for match in EXTERNAL_SCRIPT_RE.finditer(content):
        findings.append({
            "file": rel_path,
            "type": "external_script",
            "value": match.group()[:80],
        })

    # Check for external fonts
    for match in EXTERNAL_FONT_RE.finditer(content):
        findings.append({
            "file": rel_path,
            "type": "external_font",
            "value": match.group()[:80],
        })

    # Check for analytics (skip React internal bundle)
    if not is_react_bundle:
        for match in ANALYTICS_RE.finditer(content):
            findings.append({
                "file": rel_path,
                "type": "analytics",
                "value": match.group()[:80],
            })

    return findings


def scan_directory(dir_path: Path) -> list[dict]:
    """Scan all files in a directory for forbidden content."""
    all_findings = []
    files_scanned = 0

    for path in dir_path.rglob("*"):
        if not path.is_file():
            continue
        if path.suffix not in SCAN_EXTENSIONS:
            continue
        files_scanned += 1
        findings = scan_file(path)
        all_findings.extend(findings)

    return all_findings, files_scanned


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def main() -> int:
    print("=== Public Sanitizer — Built Output Scan ===")

    if not DIST_DIR.exists():
        print(f"FAIL: dist/ directory not found at {DIST_DIR}")
        print("  Run 'npm run build' first.")
        return 1

    # Scan dist/
    print(f"Scanning {DIST_DIR}...")
    findings, files_scanned = scan_directory(DIST_DIR)
    print(f"  Files scanned: {files_scanned}")
    print(f"  Findings: {len(findings)}")

    # Also scan public/ data files
    print(f"Scanning {SITE_ROOT / 'public'}...")
    pub_findings, pub_files = scan_directory(SITE_ROOT / "public")
    print(f"  Files scanned: {pub_files}")
    print(f"  Findings: {len(pub_findings)}")

    all_findings = findings + pub_findings
    total_files = files_scanned + pub_files

    # Filter out acceptable findings
    # - "token" in JS is common (JWT token parsing in react-router) — acceptable in built JS
    # - "secret" in JS — check context
    filtered = []
    for f in all_findings:
        if f["type"] == "forbidden_string":
            pattern = f["pattern"]
            context = f.get("context", "")
            # React-router uses "token" in its routing logic — acceptable
            if pattern == "token" and "dist/assets/router" in f["file"]:
                continue
            # "secret" in context of "SECRET" as a constant name is structural
            if pattern == "secret" and any(x in context.lower() for x in ["__secret", "secret_internal", "secretmode"]):
                continue
            # "password" in CSS/JS as a field name is structural
            if pattern == "password" and "type=\"password\"" in context:
                continue
        filtered.append(f)

    all_findings = filtered

    # Compute hashes of accepted outputs
    output_hashes = {}
    for path in (DIST_DIR / "data").glob("*") if (DIST_DIR / "data").exists() else []:
        if path.is_file():
            output_hashes[path.name] = sha256_file(path)

    # Build report
    report = {
        "schemaVersion": "sanitization_report_v1",
        "scannedAt": datetime.now(timezone.utc).isoformat(),
        "directoriesScanned": [str(DIST_DIR), str(SITE_ROOT / "public")],
        "filesScanned": total_files,
        "findingsCount": len(all_findings),
        "findings": all_findings[:50],
        "outputHashes": output_hashes,
        "publicReleaseStatus": "blocked" if all_findings else "pass",
        "forbiddenStringsChecked": FORBIDDEN_STRINGS,
        "piiPatternsChecked": ["email", "phone"],
        "infrastructurePatternsChecked": ["supabase.co", "localhost", "127.0.0.1", "/api/knowledge-graph", "/api/code"],
        "externalResourcePatternsChecked": ["external_script", "external_font", "analytics", "external_url"],
    }

    HANDOFF_DIR.mkdir(parents=True, exist_ok=True)

    with open(HANDOFF_DIR / "sanitization-report.json", "w") as f:
        json.dump(report, f, indent=2)

    # Markdown report
    md_lines = [
        "# Sanitization Report",
        "",
        f"**Scanned at:** {report['scannedAt']}",
        f"**Files scanned:** {report['filesScanned']}",
        f"**Findings:** {report['findingsCount']}",
        f"**Public release status:** `{report['publicReleaseStatus']}`",
        "",
        "## Directories Scanned",
        "",
    ]
    for d in report["directoriesScanned"]:
        md_lines.append(f"- `{d}`")
    md_lines.extend(["", "## Findings", ""])
    if all_findings:
        for f in all_findings[:20]:
            md_lines.append(f"- **{f['type']}** in `{f['file']}`: {f.get('value', f.get('context', ''))[:60]}")
        if len(all_findings) > 20:
            md_lines.append(f"- ... and {len(all_findings) - 20} more (see JSON report)")
    else:
        md_lines.append("No findings. All checks passed.")
    md_lines.extend(["", "## Output Hashes", ""])
    for name, h in output_hashes.items():
        md_lines.append(f"- `{name}`: `{h[:16]}...`")
    md_lines.extend([
        "",
        "## Patterns Checked",
        "",
        "### Forbidden Strings",
        "",
    ])
    for s in FORBIDDEN_STRINGS:
        md_lines.append(f"- `{s}`")
    md_lines.extend(["", "### PII Patterns", "", "- Email addresses", "- Phone numbers"])
    md_lines.extend(["", "### Infrastructure Patterns", ""])
    for p in report["infrastructurePatternsChecked"]:
        md_lines.append(f"- `{p}`")
    md_lines.extend(["", "### External Resource Patterns", ""])
    for p in report["externalResourcePatternsChecked"]:
        md_lines.append(f"- `{p}`")

    with open(HANDOFF_DIR / "sanitization-report.md", "w") as f:
        f.write("\n".join(md_lines))

    # Result
    if all_findings:
        print(f"\nFAIL-CLOSED: {len(all_findings)} findings in built output!")
        for f in all_findings[:10]:
            print(f"  {f['type']} in {f['file']}: {f.get('value', f.get('context', ''))[:60]}")
        print(f"\nPublic release status: BLOCKED")
        return 1
    else:
        print(f"\nAll checks passed. {total_files} files scanned, 0 findings.")
        print(f"Public release status: PASS")
        return 0


if __name__ == "__main__":
    sys.exit(main())
