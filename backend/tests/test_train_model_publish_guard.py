from __future__ import annotations

import unittest

try:
    from backend.train_model import publish_guard_reason
    _IMPORT_ERROR = None
except ModuleNotFoundError as exc:  # pragma: no cover - depends on optional training deps
    publish_guard_reason = None
    _IMPORT_ERROR = exc


@unittest.skipIf(publish_guard_reason is None, f'train_model import unavailable: {_IMPORT_ERROR}')
class TrainModelPublishGuardTests(unittest.TestCase):
    def test_synthetic_artifacts_are_never_published(self) -> None:
        reason = publish_guard_reason(is_synthetic=True, allow_publish=True)
        self.assertEqual(reason, 'synthetic_bootstrap_not_published')

    def test_shadow_only_remote_training_skips_publish(self) -> None:
        reason = publish_guard_reason(is_synthetic=False, allow_publish=False)
        self.assertEqual(reason, 'shadow_only_remote_training')

    def test_publish_allowed_when_real_data_and_flag_enabled(self) -> None:
        reason = publish_guard_reason(is_synthetic=False, allow_publish=True)
        self.assertIsNone(reason)


if __name__ == '__main__':
    unittest.main()
