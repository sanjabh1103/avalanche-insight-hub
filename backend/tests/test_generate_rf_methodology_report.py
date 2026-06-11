from backend.scripts.generate_rf_methodology_report import build_rf_methodology_report


def test_rf_methodology_report_preserves_baseline_boundaries():
    report = build_rf_methodology_report({
        'model_family': 'RandomForestClassifier',
        'class_weight': {'0': 1, '1': 4},
        'resampling': {'strategy': 'kmeanssmote'},
        'time_series_cv': {'mean_pss': 0.42},
        'calibration': {'method': 'isotonic'},
        'selected_features': ['snowfall_24h', 'wind_speed', 'slope'],
        'metrics': {'brier_score': 0.18, 'roc_auc': 0.76, 'pss_threshold': 0.41},
    })

    assert 'Random-Forest Methodology Baseline' in report
    assert 'kmeanssmote' in report
    assert 'isotonic' in report
    assert 'Synthetic demo rows are excluded' in report
    assert 'not a promoted MTS-LSTM, SAR FCN' in report
