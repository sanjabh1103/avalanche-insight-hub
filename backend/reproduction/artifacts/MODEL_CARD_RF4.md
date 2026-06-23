# Model Card: Swiss RAvaFcast RF4 Reproduction

**Model name**: Random Forest 4 (RF4) — Swiss Avalanche Forecast Reproduction
**Model version**: auto_numeric_current (74 features)
**Date**: 2026-06-23
**Schema**: Model Card v1 (Mitchell et al., 2019)

---

## 1. Model Details

### Architecture
- **Type**: Random Forest classifier (scikit-learn `RandomForestClassifier`)
- **Trees**: 500 estimators
- **Calibration**: Isotonic regression (per-class, one-vs-rest)
- **Feature selection**: `auto_numeric_current` (74 numeric features, leakage-guarded)

### Training Data
- **Source**: EnviDat RF2 dataset (Pérez-Guillén et al., 2024)
- **Samples**: 11,741 total (train: 5,871, calibration: 2,935, test: 2,935)
- **Region**: Swiss Alps (WGS84, ~46.0–47.7°N, 5.9–10.5°E)
- **Temporal range**: Winter 2017/18 – 2020/21
- **Labels**: 4-class avalanche danger level (1=Low, 2=Moderate, 3=Considerable, 4=High)

### Evaluation Data
- **Test split**: 2,935 samples (chronological split, last winter season)
- **Class distribution**: Class 1: 691, Class 2: 1,145, Class 3: 941, Class 4: 158

---

## 2. Intended Use

### Primary Use Cases
- Shadow benchmark for Himalayan avalanche forecasting system
- Scientific reproduction validation (RAvaFcast Stage-2)
- Feature importance analysis via TreeSHAP explainability

### Out-of-Scope Uses
- Operational avalanche warning in any region
- Direct deployment without Himalayan-specific validation
- Real-time inference (model is offline-trained only)

---

## 3. Performance Metrics

| Metric | Value |
|---|---|
| Overall accuracy | 89.37% |
| Macro F1 | 0.7474 |
| Class 4 (High) F1 | 0.3488 |
| Class 4 recall | 0.449 |
| Brier score (calibrated) | 0.157 |
| ECE (calibrated) | 0.041 |
| ECE (uncalibrated) | 0.126 |
| PSS (Peirce Skill Score) | 0.51 |

### Confusion Matrix (Test Set)

| Actual \ Predicted | 1 (Low) | 2 (Mod) | 3 (Cons) | 4 (High) |
|---|---:|---:|---:|---:|
| 1 (Low) | 621 | 70 | 0 | 0 |
| 2 (Moderate) | 51 | 960 | 134 | 0 |
| 3 (Considerable) | 0 | 129 | 798 | 14 |
| 4 (High) | 0 | 0 | 21 | 38 |

---

## 4. Top SHAP Feature Importance (TreeSHAP)

| Rank | Feature | Mean |SHAP| | Interpretation |
|---:|---|---:|---|
| 1 | `elevation_th` | 0.078 | Higher elevation → higher danger |
| 2 | `HN72_24` | 0.046 | 72h new snow height → loading driver |
| 3 | `HN24_7d` | 0.035 | 7-day new snow → persistent weak layer |
| 4 | `Pen_depth` | 0.026 | Penetration depth → snowpack stability |
| 5 | `HN24` | 0.026 | 24h new snow → immediate loading |

**Method**: TreeSHAP (SHAP values computed on 500 test samples, 74 features)

---

## 5. Calibration Reliability

| Metric | Uncalibrated | Calibrated (Isotonic) |
|---|---:|---:|
| Brier score | 0.177 | 0.157 |
| ECE | 0.126 | 0.041 |

**Calibration method**: Isotonic regression, per-class one-vs-rest
**Calibration rows**: 2,935
**Key finding**: 67% reduction in ECE after isotonic calibration

---

## 6. Ethical Considerations

- **False negatives on Class 4 (High)**: 21/59 High-danger days predicted as Considerable — potentially dangerous underestimation
- **Class imbalance**: Class 4 has only 158 samples (5.4%) — model may underperform on rare High-danger events
- **Regional bias**: Trained exclusively on Swiss Alps data; transferability to Himalayan conditions is unvalidated
- **No operational deployment**: This model is for scientific benchmarking only

---

## 7. Limitations

1. **GPxyz blocked**: Swiss station coordinates missing; no Stage-3 elevation-band aggregation
2. **No sub-level danger prediction**: Maissen et al. (2024) sub-levels not implemented
3. **No event-ratio validation**: Pérez-Guillén et al. (2025) bin-wise validation not yet computed on this model
4. **No Himalayan validation**: Transfer learning to NW Himalaya is cited but not code-implemented
5. **Snowpack proxy only**: No SNOWPACK/Crocus thermodynamic model integration

---

## 8. Reproducibility

- **Data download**: `python -m backend.reproduction.swiss_ravafcast.cli download`
- **Training**: `python -m backend.reproduction.swiss_ravafcast.cli train --feature-set auto_numeric_current`
- **SHAP computation**: `python -m backend.reproduction.swiss_ravafcast.cli shap`
- **Feature audit**: `python -m backend.reproduction.swiss_ravafcast.cli audit-features`
- **Artifacts**: `backend/reproduction/artifacts/`

---

## 9. Citations

1. Pérez-Guillén, C., et al. (2024). EnviDat RF2 dataset. Swiss Federal Institute for Forest, Snow and Landscape Research (WSL).
2. Pérez-Guillén, C., et al. (2025). Physics-informed machine learning for avalanche forecasting. *Natural Hazards and Earth System Sciences* (NHESS).
3. Mitchell, M., et al. (2019). Model Cards for Model Reporting. *FAT* 2019.
4. Lundberg, S., & Lee, S. (2017). A Unified Approach to Interpreting Model Predictions (SHAP). *NeurIPS* 2017.
