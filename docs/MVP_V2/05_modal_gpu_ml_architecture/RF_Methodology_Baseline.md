# Random-Forest Methodology Baseline

## Claim Boundary

The current MVP remains anchored on the explainable `surrogate_rf_v1` baseline. This document is a methodology baseline, not proof that the system is among the world's top three avalanche prediction services.

## Baseline Controls

| Control | Current repo support |
|---|---|
| Rare-event metric | Peirce Skill Score helpers in `backend/models/surrogate_rf.py`. |
| Class imbalance | Locked class weights plus KMeansSMOTE fallback policy. |
| Chronological validation | TimeSeriesSplit path for non-shuffled evaluation. |
| Feature discipline | RFE-selected feature subset and top feature explanations. |
| Calibration | Isotonic/sigmoid calibration fallback. |
| Claim governance | Scientist reviews can create actions, but do not auto-retrain or promote. |

## Exclusions

- Synthetic demo rows are excluded from training and methodology evidence.
- Scientist review actions are governance signals, not automatic model promotion.
- SAR FCN, MTS-LSTM, and SNOWPACK-class claims remain separate gated tracks.
