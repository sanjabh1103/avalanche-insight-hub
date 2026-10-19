from __future__ import annotations

import unittest

import numpy as np

from backend.data.mts_lstm_loader import MTSAvalancheDataset, torch
from backend.models.mts_lstm import BranchedMTSLSTM


@unittest.skipIf(torch is None or BranchedMTSLSTM is None, 'torch runtime unavailable')
class MTSLSTMTrainingStepTests(unittest.TestCase):
    def test_backward_and_optimizer_step_complete_without_runtime_error(self) -> None:
        torch.manual_seed(7)
        np.random.seed(7)

        model = BranchedMTSLSTM(
            hourly_input_size=6,
            daily_input_size=6,
            static_input_size=10,
            dropout=0.15,
        )
        dataset = MTSAvalancheDataset(
            hourly=np.random.randn(2, 24, 6).astype(np.float32),
            daily=np.random.randn(2, 7, 6).astype(np.float32),
            static=np.random.randn(2, 10).astype(np.float32),
            labels=np.asarray([1.0, 0.0], dtype=np.float32),
            sample_weights=np.asarray([0.9, 1.0], dtype=np.float32),
        )

        batch = {
            'hourly': torch.stack([dataset[0]['hourly'], dataset[1]['hourly']]),
            'daily': torch.stack([dataset[0]['daily'], dataset[1]['daily']]),
            'static': torch.stack([dataset[0]['static'], dataset[1]['static']]),
            'label': torch.stack([dataset[0]['label'], dataset[1]['label']]),
            'sample_weight': torch.stack([dataset[0]['sample_weight'], dataset[1]['sample_weight']]),
        }

        optimizer = torch.optim.AdamW(model.parameters(), lr=1e-3)
        loss_fn = torch.nn.BCEWithLogitsLoss(pos_weight=torch.tensor([1.0]), reduction='none')

        optimizer.zero_grad()
        logits = model(batch['hourly'], batch['daily'], batch['static'])
        loss = (loss_fn(logits, batch['label']) * batch['sample_weight']).mean()
        loss.backward()

        grad_params = sum(1 for parameter in model.parameters() if parameter.grad is not None)
        nonzero_grad_params = sum(
            1
            for parameter in model.parameters()
            if parameter.grad is not None and torch.count_nonzero(parameter.grad).item() > 0
        )

        optimizer.step()

        self.assertEqual(tuple(logits.shape), (2,))
        self.assertGreater(grad_params, 0)
        self.assertGreater(nonzero_grad_params, 0)


if __name__ == '__main__':
    unittest.main()
