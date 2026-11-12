from __future__ import annotations

import os
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

from backend.common.track_contracts.lane_execution_wrapper import LaneExecutionError
from backend.scripts.run_modal_sar_checkpoint_evaluation_direct import (
    run_modal_sar_checkpoint_evaluation_direct,
)
from backend.scripts.run_modal_sar_prediction_materialization_direct import (
    run_modal_sar_prediction_materialization_direct,
)
from backend.scripts.run_modal_sar_release_evaluation_direct import (
    run_modal_sar_release_evaluation_direct,
)
from backend.scripts.run_modal_sar_training_direct import (
    run_modal_sar_training_async,
    run_modal_sar_training_direct,
)


class ModalSubmissionGateTests(unittest.TestCase):
    def test_explicit_lane_direct_submissions_block_before_modal_resolution(self) -> None:
        """Direct CLI paths must not resolve, remote, or spawn blocked lane work."""
        submissions = (
            (
                'backend.scripts.run_modal_sar_training_direct',
                run_modal_sar_training_direct,
                'training',
            ),
            (
                'backend.scripts.run_modal_sar_training_direct',
                run_modal_sar_training_async,
                'training',
            ),
            (
                'backend.scripts.run_modal_sar_release_evaluation_direct',
                run_modal_sar_release_evaluation_direct,
                'evaluation',
            ),
            (
                'backend.scripts.run_modal_sar_checkpoint_evaluation_direct',
                run_modal_sar_checkpoint_evaluation_direct,
                'evaluation',
            ),
            (
                'backend.scripts.run_modal_sar_prediction_materialization_direct',
                run_modal_sar_prediction_materialization_direct,
                'serve',
            ),
        )

        with patch.dict(os.environ, {}, clear=True):
            for track in ('t2a', 'track1'):
                for module_name, submitter, operation_mode in submissions:
                    from_name = Mock()
                    fake_modal = SimpleNamespace(
                        Function=SimpleNamespace(from_name=from_name),
                    )
                    with self.subTest(track=track, submitter=submitter.__name__):
                        with patch(
                            f'{module_name}._load_modal_module',
                            return_value=fake_modal,
                        ) as load_modal:
                            with self.assertRaises(LaneExecutionError) as caught:
                                submitter(
                                    modal_profile='test-profile',
                                    request_payload={
                                        'Partner_lane': True,
                                        'track': track,
                                        'operation_mode': operation_mode,
                                    },
                                )

                        self.assertIn('E024_missing_evidence_packet', str(caught.exception))
                        load_modal.assert_not_called()
                        from_name.assert_not_called()


if __name__ == '__main__':
    unittest.main()
