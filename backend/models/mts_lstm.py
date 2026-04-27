from __future__ import annotations

try:  # pragma: no cover - optional dependency at import time
    import torch
except Exception:  # pragma: no cover - optional dependency
    torch = None


if torch is not None:
    # Governance rule:
    # - Never apply KMeansSMOTE to the hourly/daily sequence tensors consumed by
    #   this model. Sequence-space interpolation destroys temporal structure and
    #   is not a credible production training path for the branched MTS-LSTM.
    # - Class imbalance for this model family is handled with weighted sampling
    #   and class-weighted / focal-loss style objectives.
    # - KMeansSMOTE remains limited to the tabular/tree surrogate path.
    class BranchedMTSLSTM(torch.nn.Module):
        def __init__(
            self,
            hourly_input_size: int,
            daily_input_size: int,
            static_input_size: int,
            *,
            dropout: float = 0.15,
        ) -> None:
            super().__init__()
            self.hourly_lstm = torch.nn.LSTM(
                input_size=hourly_input_size,
                hidden_size=32,
                num_layers=1,
                batch_first=True,
            )
            self.daily_lstm = torch.nn.LSTM(
                input_size=daily_input_size,
                hidden_size=24,
                num_layers=1,
                batch_first=True,
            )
            self.static_encoder = torch.nn.Sequential(
                torch.nn.Linear(static_input_size, 16),
                torch.nn.ReLU(),
                torch.nn.Dropout(dropout),
            )
            self.head = torch.nn.Sequential(
                torch.nn.Linear(32 + 24 + 16, 32),
                torch.nn.ReLU(),
                torch.nn.Dropout(dropout),
                torch.nn.Linear(32, 1),
            )

        def forward(self, hourly: torch.Tensor, daily: torch.Tensor, static: torch.Tensor) -> torch.Tensor:
            hourly_out, _ = self.hourly_lstm(hourly)
            daily_out, _ = self.daily_lstm(daily)
            static_out = self.static_encoder(static)
            merged = torch.cat([hourly_out[:, -1, :], daily_out[:, -1, :], static_out], dim=1)
            return self.head(merged).squeeze(-1)
else:  # pragma: no cover - exercised only when torch missing
    BranchedMTSLSTM = None
