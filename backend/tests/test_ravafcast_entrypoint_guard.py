"""Fail-closed guard for the extracted inference package."""
from __future__ import annotations

import unittest
import ast
import subprocess
import sys
from pathlib import Path


class RavafcastEntrypointGuardTests(unittest.TestCase):
    def test_extracted_orchestrator_is_not_a_runtime_entrypoint(self) -> None:
        from backend.inference import require_canonical_runtime

        with self.assertRaises(RuntimeError):
            require_canonical_runtime('backend.inference.orchestrator')

    def test_daily_inference_is_the_canonical_entrypoint(self) -> None:
        from backend.inference import require_canonical_runtime

        require_canonical_runtime('backend.daily_inference')

    def test_inference_package_does_not_eagerly_import_extracted_runtime(self) -> None:
        result = subprocess.run(
            [
                sys.executable,
                '-c',
                'import sys; import backend.inference; '
                'print("backend.inference.orchestrator" in sys.modules)',
            ],
            check=True,
            capture_output=True,
            text=True,
        )
        self.assertEqual(result.stdout.strip(), 'False')

    def test_active_main_calls_carry_cadence_context(self) -> None:
        source = Path(__file__).parents[1].joinpath('daily_inference.py').read_text()
        tree = ast.parse(source)
        main = next(node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == 'main')
        calls = [
            node for node in ast.walk(main)
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id in {'build_hourly_grids', 'upsert_forecast_grid'}
        ]
        self.assertEqual(len(calls), 2)
        for call in calls:
            self.assertIn('cadence_context', {kw.arg for kw in call.keywords})
            cadence_kw = next(kw for kw in call.keywords if kw.arg == 'cadence_context')
            self.assertIsInstance(cadence_kw.value, ast.Name)
            self.assertEqual(cadence_kw.value.id, '_cadence_context')

    def test_publication_call_reads_cadence_context_attributes(self) -> None:
        source = Path(__file__).parents[1].joinpath('daily_inference.py').read_text()
        tree = ast.parse(source)
        upsert = next(
            node for node in ast.walk(tree)
            if isinstance(node, ast.FunctionDef) and node.name == 'upsert_forecast_grid'
        )
        publish = next(
            node for node in ast.walk(upsert)
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == 'publish_forecast_run'
        )
        expressions = {
            kw.arg: [child for child in ast.walk(kw.value) if isinstance(child, ast.Attribute)]
            for kw in publish.keywords
        }
        self.assertTrue(any('cadence_context' in ast.unparse(attr) for attr in expressions['issue_slot']))
        self.assertTrue(any('cadence_context.valid_from' in ast.unparse(attr) for attr in expressions['valid_from']))

    def test_disconnected_call_fixture_is_rejected(self) -> None:
        fixture = ast.parse(
            'def main():\n'
            '    build_hourly_grids(region, bundle, grid_size=20)\n'
        )
        call = next(node for node in ast.walk(fixture) if isinstance(node, ast.Call))
        self.assertNotIn('cadence_context', {kw.arg for kw in call.keywords})


if __name__ == '__main__':
    unittest.main()
