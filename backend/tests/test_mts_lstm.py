from __future__ import annotations

import unittest

from backend.models.mts_lstm import BranchedMTSLSTM, torch


@unittest.skipIf(torch is None or BranchedMTSLSTM is None, 'torch runtime unavailable')
class BranchedMTSLSTMTests(unittest.TestCase):
    def test_forward_returns_one_logit_per_batch_row(self) -> None:
        model = BranchedMTSLSTM(
            hourly_input_size=6,
            daily_input_size=6,
            static_input_size=10,
            dropout=0.2,
        )
        hourly = torch.zeros((3, 24, 6), dtype=torch.float32)
        daily = torch.zeros((3, 7, 6), dtype=torch.float32)
        static = torch.zeros((3, 10), dtype=torch.float32)

        logits = model(hourly, daily, static)

        self.assertEqual(tuple(logits.shape), (3,))


if __name__ == '__main__':
    unittest.main()
