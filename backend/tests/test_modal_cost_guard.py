from __future__ import annotations

import os
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

from backend.scripts.modal_cost_guard import DEFAULT_GPU_FUNCTIONS, reassert_modal_zero_warm_autoscaler


class ModalCostGuardTests(unittest.TestCase):
    def test_reassert_modal_zero_warm_autoscaler_updates_named_functions(self) -> None:
        functions = {}

        def from_name(app_name, function_name):
            function = Mock()
            functions[(app_name, function_name)] = function
            return function

        fake_modal = SimpleNamespace(Function=SimpleNamespace(from_name=from_name))

        with patch('backend.scripts.modal_cost_guard._load_modal_module', return_value=fake_modal), \
                patch.dict(os.environ, {}, clear=True):
            result = reassert_modal_zero_warm_autoscaler(
                modal_profile='sanjabh1103_limit30',
                app_name='avalanche-modal-worker',
                function_names=('sar_segment_remote', 'train_sar_unet_remote'),
                scaledown_window=30,
            )

        self.assertEqual(result['status'], 'ok')
        self.assertEqual(result['modal_profile'], 'sanjabh1103_limit30')
        self.assertEqual(len(result['updates']), 2)
        for function in functions.values():
            function.update_autoscaler.assert_called_once_with(
                min_containers=0,
                buffer_containers=0,
                scaledown_window=30,
            )

    def test_default_gpu_functions_include_checkpoint_evaluation(self) -> None:
        self.assertIn('evaluate_sar_checkpoint_remote', DEFAULT_GPU_FUNCTIONS)


if __name__ == '__main__':
    unittest.main()
