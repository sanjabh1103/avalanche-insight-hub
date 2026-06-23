# Pre-Meeting Email — June 23, 2026

**To:** Dr. Amreek Singh
**Cc:** Dr. Praven (second group)
**Subject:** Progress update and pre-read materials for tomorrow's discussion

---

Dear Dr. Amreek,

Thank you for confirming the meeting tomorrow. I wanted to share a brief update on where we stand, so that our discussion can focus on your feedback and ideas rather than spending time on basic questions.

Since our last correspondence, we have made progress on the autonomous model direction you emphasised — the one that requires no historical data and no manual observations. Specifically:

1. **Probabilistic weather integration:** We have wired the Open-Meteo Ensemble API into the inference pipeline. The system now carries p10/p50/p90 percentile bands for temperature, snowfall, and precipitation alongside the deterministic forecast. This means we can show uncertainty ranges from ensemble weather models, not just single-point values.

2. **Calibration validation framework:** We implemented the event ratio binning methodology from the NHESS 2025 literature — binning predicted probabilities and comparing against observed event ratios. This gives us a formal way to answer "how well-calibrated are the probabilities?" rather than relying on accuracy alone.

3. **Temporal persistence features:** The feature pipeline now computes 24h and 72h rolling snowfall, snow-loading persistence, and sub-zero temperature persistence. This captures the "ripening" period that your own work has identified — avalanching conditions develop over 2-3 days, not instantaneously.

4. **SHAP explanations in plain language:** Every forecast cell now generates a human-readable explanation of its primary risk drivers (e.g., "Primary risk drivers: elevation, new snow height, wind transport"). This is in addition to the numeric SHAP values — so a forecaster can read why a cell is rated the way it is without interpreting a bar chart.

5. **Model card for the Swiss RF4 reproduction:** We prepared a formal model card (Mitchell et al., 2019 schema) documenting the architecture, training data, performance metrics, SHAP importance, calibration, ethical considerations, and limitations of the Swiss RF4 reproduction. This is attached for your reference.

I have also attached a FAQ sheet that addresses 31 questions we anticipate from the scientist team. It covers class imbalance handling, feature selection, AWS dependency elimination, risk fusion methodology, validation metrics, TreeSHAP explainability, the Swiss RAvaFcast comparison, NATSAT complementarity, HIM-STRAT alignment, and the DRDO-ISRO MoU. The intent is that once you begin the presentation, typical questions are already answered and we can spend our time on substance.

A few things I want to be clear about:
- The autonomous pipeline generates its own training data. No historical datasets, station data, or snowpack profiles are required from your team to activate it.
- We need only three things from you: a scientist point of contact, 1-2 suggested pilot regions, and operational feedback on pipeline output.
- We explicitly invite your ideas for augmentation — you mentioned having ideas to further augment this approach, and we would like to hear them.

The hosted prototype is available at https://avalanche-insight-hub.netlify.app for your review before the meeting.

Looking forward to the discussion tomorrow.

With regards,
Sanjay

---

**Attachments:**
1. `SCIENTIST_DEMO_FAQ_SHEET.md` — 31 expected questions with evidence-grounded answers
2. `MODEL_CARD_RF4.md` — Formal model card for Swiss RF4 reproduction (Mitchell et al., 2019 schema)
