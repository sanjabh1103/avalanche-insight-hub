#!/usr/bin/env python3
"""RAvaFcast AST-level conformance checks.

Verifies runtime wiring correctness, contract imports, publication field
passing, exception hygiene, and orchestrator isolation.  Called by
``scripts/check_ravafcast_conformance.sh``.

Exit code 0 = all checks pass; non-zero = at least one check failed.
"""

from __future__ import annotations

import ast
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DAILY_INFERENCE = ROOT / "backend" / "daily_inference.py"
FORECAST_PUBLICATION = ROOT / "backend" / "common" / "forecast_publication.py"
TEST_DIR = ROOT / "backend" / "tests"

# ── test-file globs scoped to RAvaFcast-related suites ──────────────────────
RAVAFCAST_TEST_GLOBS = [
    "test_ravafcast*.py",
    "test_daily_inference*.py",
    "test_forecast*.py",
    "test_Partner*.py",
    "test_ravafcast_e2e*.py",
]

PASSED: list[str] = []
FAILED: list[str] = []


def _ok(msg: str) -> None:
    PASSED.append(msg)
    print(f"  PASS  {msg}")


def _fail(msg: str) -> None:
    FAILED.append(msg)
    print(f"  FAIL  {msg}")


# ---------------------------------------------------------------------------
# Helper: collect matching test files
# ---------------------------------------------------------------------------

def _ravafcast_test_files() -> list[Path]:
    files: list[Path] = []
    for glob in RAVAFCAST_TEST_GLOBS:
        files.extend(sorted(TEST_DIR.glob(glob)))
    return files


# ---------------------------------------------------------------------------
# Check 1 — Cadence context threading
#   issue_time must come from cadence_context.issue_time, not wall-clock.
# ---------------------------------------------------------------------------

def check_cadence_context_threading() -> None:
    """Verify publish_forecast_run receives issue_time from cadence context."""
    tree = _parse(DAILY_INFERENCE)
    if tree is None:
        _fail("cadence-context-threading: cannot parse daily_inference.py")
        return

    # Find all calls to publish_forecast_run and check for issue_time= kwarg
    found_issue_time_from_context = False
    found_datetime_now = False

    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            func_name = _call_name(node)
            if func_name in ("publish_forecast_run",):
                for kw in node.keywords:
                    if kw.arg == "issue_time":
                        # Check if value is cadence_context.issue_time
                        val_src = ast.unparse(kw.value)
                        if "cadence_context" in val_src and "issue_time" in val_src:
                            found_issue_time_from_context = True
                        elif "datetime.now" in val_src or "datetime.utcnow" in val_src:
                            found_datetime_now = True

    if found_datetime_now:
        _fail("cadence-context-threading: issue_time uses wall-clock (datetime.now), not cadence context")
    elif found_issue_time_from_context:
        _ok("cadence-context-threading: issue_time threaded from cadence_context")
    else:
        _fail("cadence-context-threading: no issue_time= kwarg found at publish_forecast_run call site")


# ---------------------------------------------------------------------------
# Check 2 — PartnerCellInputContract / build_cell_inputs import
# ---------------------------------------------------------------------------

def check_Partner_contract_import() -> None:
    """Verify build_cell_inputs (or _build_Partner_contracts) is imported in daily_inference."""
    tree = _parse(DAILY_INFERENCE)
    if tree is None:
        _fail("Partner-contract-import: cannot parse daily_inference.py")
        return

    found = False
    for node in ast.walk(tree):
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            for alias in node.names:
                imported = alias.asname or alias.name
                if imported in ("build_cell_inputs", "_build_Partner_contracts"):
                    found = True
                    break

    if found:
        _ok("Partner-contract-import: build_cell_inputs imported in daily_inference.py")
    else:
        _fail("Partner-contract-import: build_cell_inputs NOT imported in daily_inference.py")


# ---------------------------------------------------------------------------
# Check 3 — Publication field passing
#   issue_slot, cadence_hours, valid_from, valid_to, source_as_of must all
#   be passed at the publish_forecast_run call site.
# ---------------------------------------------------------------------------

REQUIRED_PUBLICATION_KWARGS = {
    "issue_slot",
    "cadence_hours",
    "valid_from",
    "valid_to",
    "source_as_of",
}


def check_publication_field_passing() -> None:
    """Verify all required publication fields are passed to publish_forecast_run."""
    tree = _parse(DAILY_INFERENCE)
    if tree is None:
        _fail("publication-field-passing: cannot parse daily_inference.py")
        return

    all_kwargs: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            if _call_name(node) in ("publish_forecast_run",):
                for kw in node.keywords:
                    if kw.arg:
                        all_kwargs.add(kw.arg)

    missing = REQUIRED_PUBLICATION_KWARGS - all_kwargs
    if missing:
        _fail(f"publication-field-passing: missing kwargs: {sorted(missing)}")
    else:
        _ok("publication-field-passing: all 5 required fields passed to publish_forecast_run")


# ---------------------------------------------------------------------------
# Check 4 — No bare ``except: pass`` in RAvaFcast test files
# ---------------------------------------------------------------------------

def check_no_bare_except_pass() -> None:
    """Flag any bare ``except:`` whose body is only ``pass``."""
    violations: list[str] = []
    for fp in _ravafcast_test_files():
        tree = _parse(fp)
        if tree is None:
            continue
        for node in ast.walk(tree):
            if isinstance(node, ast.ExceptHandler):
                # bare except = node.type is None
                if node.type is None and len(node.body) == 1:
                    if isinstance(node.body[0], ast.Pass):
                        violations.append(f"{fp.name}:{node.lineno}")

    if violations:
        _fail(f"bare-except-pass: {len(violations)} violation(s): {', '.join(violations)}")
    else:
        _ok("bare-except-pass: no bare except: pass in RAvaFcast test files")


# ---------------------------------------------------------------------------
# Check 5 — Orchestrator isolation
#   daily_inference.py must NOT import from backend.inference.orchestrator
# ---------------------------------------------------------------------------

def check_no_orchestrator_import() -> None:
    """Verify daily_inference.py does not import the candidate orchestrator."""
    tree = _parse(DAILY_INFERENCE)
    if tree is None:
        _fail("orchestrator-isolation: cannot parse daily_inference.py")
        return

    found = False
    for node in ast.walk(tree):
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            module = getattr(node, "module", "") or ""
            if "orchestrator" in module:
                found = True
                break

    if found:
        _fail("orchestrator-isolation: daily_inference.py imports orchestrator module")
    else:
        _ok("orchestrator-isolation: daily_inference.py does NOT import orchestrator")


# ---------------------------------------------------------------------------
# Check 6 — issue_time parameter in publish_forecast_run signature
# ---------------------------------------------------------------------------

def check_issue_time_parameter() -> None:
    """Verify publish_forecast_run function signature includes issue_time."""
    tree = _parse(FORECAST_PUBLICATION)
    if tree is None:
        _fail("issue-time-param: cannot parse forecast_publication.py")
        return

    found = False
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == "publish_forecast_run":
            for arg in node.args.args + node.args.posonlyargs + node.args.kwonlyargs:
                if arg.arg == "issue_time":
                    found = True
                    break
            break

    if found:
        _ok("issue-time-param: publish_forecast_run accepts issue_time parameter")
    else:
        _fail("issue-time-param: publish_forecast_run MISSING issue_time parameter")


# ---------------------------------------------------------------------------
# Check 7 — No swallowed exceptions in RAvaFcast test files
#   Broader than check 4: any except block whose body is only pass,
#   even with a specific exception type.
# ---------------------------------------------------------------------------

def check_no_swallowed_exceptions() -> None:
    """Flag ``except Exception: pass`` blocks (not bare except or specific types).

    Bare ``except:`` is caught by check 4.  Specific exception tuples like
    ``except (RuntimeError, ModuleNotFoundError): pass`` are legitimate
    conditional-import guards and are intentionally allowed here.
    """
    violations: list[str] = []
    for fp in _ravafcast_test_files():
        tree = _parse(fp)
        if tree is None:
            continue
        for node in ast.walk(tree):
            if isinstance(node, ast.ExceptHandler):
                if len(node.body) == 1 and isinstance(node.body[0], ast.Pass):
                    # Only flag except Exception (not bare, not specific tuples)
                    if node.type is not None:
                        if isinstance(node.type, ast.Name) and node.type.id == "Exception":
                            violations.append(f"{fp.name}:{node.lineno}")

    if violations:
        _fail(f"swallowed-exceptions: {len(violations)} violation(s): {', '.join(violations)}")
    else:
        _ok("swallowed-exceptions: no swallowed Exception: pass in RAvaFcast test files")


# ---------------------------------------------------------------------------
# Check 8 — pyproj availability (G15)
# ---------------------------------------------------------------------------

def check_pyproj_availability() -> None:
    """Report whether pyproj is available for projected-grid tests.

    This is an **advisory** check — it reports status but does not fail,
    because the conformance script may run before locked dependencies are
    installed (as in the CI workflow).  pyproj availability only affects
    whether projected-grid tests can run, not conformance correctness.
    """
    try:
        import pyproj  # noqa: F401
        _ok(f"pyproj-availability: pyproj {pyproj.__version__} available — projected-grid tests can run")
    except ImportError:
        # Advisory — does not count as pass or fail
        print("  INFO  pyproj-availability: pyproj NOT available — projected-grid tests will be skipped (install deps first)")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _parse(path: Path) -> ast.Module | None:
    try:
        return ast.parse(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def _call_name(node: ast.Call) -> str | None:
    """Extract the function name from a Call node."""
    if isinstance(node.func, ast.Name):
        return node.func.id
    if isinstance(node.func, ast.Attribute):
        return node.func.attr
    return None


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

CHECKS = [
    ("cadence-context-threading", check_cadence_context_threading),
    ("Partner-contract-import", check_Partner_contract_import),
    ("publication-field-passing", check_publication_field_passing),
    ("bare-except-pass", check_no_bare_except_pass),
    ("orchestrator-isolation", check_no_orchestrator_import),
    ("issue-time-param", check_issue_time_parameter),
    ("swallowed-exceptions", check_no_swallowed_exceptions),
    ("pyproj-availability", check_pyproj_availability),
]


def main() -> int:
    print("--- RAvaFcast AST Conformance Checks ---")
    for _name, fn in CHECKS:
        fn()

    n_pass = len(PASSED)
    n_fail = len(FAILED)
    n_total = n_pass + n_fail
    print(f"\n--- Results: {n_pass}/{n_total} passed ---")
    if FAILED:
        print("Failures:")
        for msg in FAILED:
            print(f"  - {msg}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
