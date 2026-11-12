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

    class ZoneAttentionGate(torch.nn.Module):
        """Lightweight attention gate conditioned on zone one-hot vector.

        Produces 2 softmax weights that re-weight hourly vs daily LSTM outputs.
        When zone_type is None (all-zeros input), defaults to uniform [0.5, 0.5].
        """

        def __init__(self, zone_dim: int = 4) -> None:
            super().__init__()
            self.gate = torch.nn.Linear(zone_dim, 2)

        def forward(self, zone_onehot: torch.Tensor) -> torch.Tensor:
            return torch.softmax(self.gate(zone_onehot), dim=-1)

    class BranchedMTSLSTM(torch.nn.Module):
        def __init__(
            self,
            hourly_input_size: int,
            daily_input_size: int,
            static_input_size: int,
            *,
            dropout: float = 0.15,
            zone_dim: int = 4,
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
            self.zone_gate = ZoneAttentionGate(zone_dim)
            self.head = torch.nn.Sequential(
                torch.nn.Linear(32 + 24 + 16, 32),
                torch.nn.ReLU(),
                torch.nn.Dropout(dropout),
                torch.nn.Linear(32, 1),
            )

        def forward(
            self,
            hourly: torch.Tensor,
            daily: torch.Tensor,
            static: torch.Tensor,
            zone_onehot: torch.Tensor | None = None,
        ) -> torch.Tensor:
            hourly_out, _ = self.hourly_lstm(hourly)
            daily_out, _ = self.daily_lstm(daily)

            # F2: Split static into base features and zone one-hot if concatenated
            base_dim = self.static_encoder[0].in_features
            if static.shape[-1] > base_dim:
                base_static = static[..., :base_dim]
                embedded_zone = static[..., base_dim:]
            else:
                base_static = static
                embedded_zone = None

            static_out = self.static_encoder(base_static)

            hourly_last = hourly_out[:, -1, :]
            daily_last = daily_out[:, -1, :]

            # Use explicitly passed zone_onehot, or extract from concatenated static
            effective_zone = zone_onehot if zone_onehot is not None else embedded_zone

            if effective_zone is not None:
                gate_weights = self.zone_gate(effective_zone)
                # Apply as scalar multipliers per branch (branches have different dims)
                merged_seq = torch.cat([
                    gate_weights[:, 0:1] * hourly_last,
                    gate_weights[:, 1:2] * daily_last,
                ], dim=1)
            else:
                merged_seq = torch.cat([hourly_last, daily_last], dim=1)

            merged = torch.cat([merged_seq, static_out], dim=1)
            return self.head(merged).squeeze(-1)

        def get_attention_weights(self, zone_onehot: torch.Tensor) -> torch.Tensor:
            """Extract attention weights for F18 explainability.

            Returns [hourly_weight, daily_weight] per sample.
            """
            return self.zone_gate(zone_onehot)
else:  # pragma: no cover - exercised only when torch missing
    BranchedMTSLSTM = None
