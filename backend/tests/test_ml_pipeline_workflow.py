from pathlib import Path
import re
import unittest

from backend.common.regions import load_regions, repo_root


def _workflow_text() -> str:
    return (repo_root() / '.github' / 'workflows' / 'ml_pipeline.yml').read_text(encoding='utf-8')


class MlPipelineWorkflowTest(unittest.TestCase):
    def test_defaults_to_all_configured_public_regions(self) -> None:
        text = _workflow_text()
        expected_keys = [region.key for region in load_regions()]
        expected_csv = ','.join(expected_keys)

        self.assertIn(f"default: '{expected_csv}'", text)
        self.assertIn(f"github.event.inputs.region_keys || '{expected_csv}'", text)
        self.assertIn('REQUIRE_FULL_GRID_PUBLICATION:', text)
        self.assertIn('proof_args=(--require-same-day-publication)', text)
        self.assertIn('proof_args+=(--require-full-grid-publication)', text)

    def test_inference_trains_when_artifact_missing(self) -> None:
        text = _workflow_text()
        fallback_step = re.search(
            r"- name: Train model if inference artifact is unavailable(?P<body>.*?)- name: Run daily inference",
            text,
            flags=re.DOTALL,
        )

        self.assertIsNotNone(fallback_step)
        body = fallback_step.group('body') if fallback_step else ''
        self.assertIn('find backend/artifacts -name model.joblib', body)
        self.assertIn('python -m backend.train_model', body)
        self.assertNotIn('synthetic', body.lower())


if __name__ == '__main__':
    unittest.main()
