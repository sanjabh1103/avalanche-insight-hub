"""Shared status and schema constants for the interval-training evidence lane."""

from __future__ import annotations


INTERVAL_TRAINING_CONTRACT_VERSION = "interval_censored_training_contract_v1"
INTERVAL_TRAINING_PREPARATION_VERSION = "interval_training_preparation_v1"

# The contract and preparation implementation are present, but the existing
# timestamp-only model path must not consume this lane until its scientific
# approvals and interval loss/negative-sampling semantics are complete.
INTERVAL_TRAINING_PATH_STATUS = "implemented_shadow_only"
INTERVAL_NEGATIVE_SAMPLING_STATUS = "defined_shadow_only"
# The formula is implemented for shadow diagnostics, but its use for model
# fitting still requires scientist/customer approval below.
INTERVAL_LOSS_IMPLEMENTATION_STATUS = "defined_shadow_only"
INTERVAL_LOSS_SEMANTICS_STATUS = "pending_scientist_approval"
