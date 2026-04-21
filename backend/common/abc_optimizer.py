"""P1.1: Artificial Bee Colony optimizer for edge feature weights.

The production edge path (`supabase/functions/run-forecast/index.ts::computeRisk`)
combines normalized features with a weight vector to produce a risk score. Those
weights were previously hardcoded fallbacks when the Modal GPU worker was
unavailable. This module runs a lightweight ABC swarm on top of the real
training data and publishes the winning weights to `model_status.optimization_summary`
so the edge path consumes a genuinely tuned aggregator even without GPU.

Design:
    * Each bee position is a K-dim simplex vector (non-negative, sums to 1.0).
    * Fitness is the threshold-free Peirce Skill Score (Youden's J) of the
      linear aggregator on a hold-out slice of the training frame.
    * Convergence when best fitness improves by < `epsilon` for `patience`
      generations, or `max_iter` is reached.

No external deps beyond numpy — designed to run in GitHub Actions with the
same `requirements.txt` that trains the model.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

import numpy as np
import pandas as pd

from sklearn.metrics import roc_curve


ABC_DEFAULT_FEATURES: tuple[str, ...] = (
    'snowfall_24h',
    'wind_loading',
    'slope',
    'elevation',
    'temp_gradient',
    'snowpack',
    'ram_hardness',
    'shear_strength',
    'settlement_rate',
    'aspect_loading',
)


@dataclass(frozen=True)
class ABCResult:
    feature_weights: dict[str, float]
    holdout_pss: float
    holdout_threshold: float
    iterations: int
    population_size: int
    origin: str = 'backend_abc'


def _peirce_skill_score_max(y_true: np.ndarray, y_score: np.ndarray) -> tuple[float, float]:
    y_true_arr = np.asarray(y_true).astype(int)
    y_score_arr = np.asarray(y_score).astype(float)
    if y_true_arr.size == 0 or len(np.unique(y_true_arr)) < 2:
        return 0.0, 0.5
    try:
        fpr, tpr, thresholds = roc_curve(y_true_arr, y_score_arr)
    except Exception:
        return 0.0, 0.5
    j = tpr - fpr
    idx = int(np.argmax(j))
    return float(j[idx]), float(thresholds[idx])


def _sanitize_features(frame: pd.DataFrame, feature_columns: Sequence[str]) -> tuple[np.ndarray, list[str]]:
    resolved = [f for f in feature_columns if f in frame.columns]
    if not resolved:
        raise ValueError('No optimizer features present in training frame')
    matrix = frame[resolved].astype(float).to_numpy()
    matrix = np.clip(matrix, 0.0, 1.0)
    return matrix, resolved


def _normalize_weights(weights: np.ndarray) -> np.ndarray:
    weights = np.clip(weights, 0.0, None)
    total = weights.sum()
    if total <= 1e-9:
        return np.full_like(weights, 1.0 / max(1, len(weights)))
    return weights / total


def _evaluate(weights: np.ndarray, x: np.ndarray, y: np.ndarray) -> tuple[float, float]:
    score = x @ weights
    return _peirce_skill_score_max(y, score)


def optimize(
    frame: pd.DataFrame,
    *,
    feature_columns: Sequence[str] = ABC_DEFAULT_FEATURES,
    population_size: int = 16,
    max_iter: int = 40,
    patience: int = 6,
    epsilon: float = 1e-4,
    holdout_fraction: float = 0.2,
    seed: int = 42,
) -> ABCResult:
    """Optimize feature weights against a held-out slice of `frame`.

    Returns an ABCResult with normalized weights that sum to 1.0.
    """
    if 'label' not in frame.columns:
        raise ValueError('ABC optimizer requires a label column')

    ordered = frame.sort_values('timestamp').reset_index(drop=True) if 'timestamp' in frame.columns else frame.reset_index(drop=True)
    holdout_size = max(16, int(len(ordered) * holdout_fraction))
    if holdout_size >= len(ordered):
        raise ValueError('Training frame too small for ABC optimization hold-out')
    train_df = ordered.iloc[:-holdout_size]
    holdout_df = ordered.iloc[-holdout_size:]

    x_train, resolved = _sanitize_features(train_df, feature_columns)
    x_holdout, _ = _sanitize_features(holdout_df, resolved)
    y_train = train_df['label'].astype(int).to_numpy()
    y_holdout = holdout_df['label'].astype(int).to_numpy()

    if len(np.unique(y_train)) < 2 or len(np.unique(y_holdout)) < 2:
        raise ValueError('Label column is degenerate; ABC optimizer requires both classes in train and hold-out')

    rng = np.random.default_rng(seed)
    n_features = x_train.shape[1]

    # Seed the swarm with the current production fallback weights plus random perturbations
    seed_vector = np.array([
        0.24, 0.19, 0.17, 0.11, 0.10, 0.08, 0.04, 0.04, 0.03, 0.07
    ], dtype=float)
    if seed_vector.size != n_features:
        seed_vector = np.full(n_features, 1.0 / n_features, dtype=float)

    population = np.zeros((population_size, n_features), dtype=float)
    population[0] = _normalize_weights(seed_vector)
    for i in range(1, population_size):
        perturbation = rng.dirichlet(alpha=np.ones(n_features) * 0.6)
        population[i] = perturbation

    fitness = np.array([_evaluate(w, x_train, y_train)[0] for w in population])
    trials = np.zeros(population_size, dtype=int)
    abandon_limit = max(4, int(population_size * 0.6))

    best_idx = int(np.argmax(fitness))
    best_weights = population[best_idx].copy()
    best_fitness = float(fitness[best_idx])
    stagnation = 0
    iteration = 0

    for iteration in range(max_iter):
        # Employed bees
        for i in range(population_size):
            k = rng.integers(0, population_size - 1)
            if k >= i:
                k += 1
            dim = rng.integers(0, n_features)
            phi = rng.uniform(-1.0, 1.0)
            candidate = population[i].copy()
            candidate[dim] = candidate[dim] + phi * (candidate[dim] - population[k][dim])
            candidate = _normalize_weights(candidate)
            cand_fit, _ = _evaluate(candidate, x_train, y_train)
            if cand_fit > fitness[i]:
                population[i] = candidate
                fitness[i] = cand_fit
                trials[i] = 0
            else:
                trials[i] += 1

        # Onlooker bees: pick proportional to fitness
        prob = np.clip(fitness, 1e-6, None)
        prob = prob / prob.sum()
        for _ in range(population_size):
            i = int(rng.choice(population_size, p=prob))
            k = rng.integers(0, population_size - 1)
            if k >= i:
                k += 1
            dim = rng.integers(0, n_features)
            phi = rng.uniform(-1.0, 1.0)
            candidate = population[i].copy()
            candidate[dim] = candidate[dim] + phi * (candidate[dim] - population[k][dim])
            candidate = _normalize_weights(candidate)
            cand_fit, _ = _evaluate(candidate, x_train, y_train)
            if cand_fit > fitness[i]:
                population[i] = candidate
                fitness[i] = cand_fit
                trials[i] = 0
            else:
                trials[i] += 1

        # Scout: replace abandoned bees
        for i in range(population_size):
            if trials[i] > abandon_limit:
                population[i] = rng.dirichlet(alpha=np.ones(n_features) * 0.6)
                fitness[i], _ = _evaluate(population[i], x_train, y_train)
                trials[i] = 0

        # Track global best
        idx = int(np.argmax(fitness))
        if fitness[idx] > best_fitness + epsilon:
            best_fitness = float(fitness[idx])
            best_weights = population[idx].copy()
            stagnation = 0
        else:
            stagnation += 1
        if stagnation >= patience:
            break

    holdout_pss, holdout_threshold = _evaluate(best_weights, x_holdout, y_holdout)

    return ABCResult(
        feature_weights={f: float(w) for f, w in zip(resolved, best_weights)},
        holdout_pss=holdout_pss,
        holdout_threshold=holdout_threshold,
        iterations=iteration + 1,
        population_size=population_size,
    )


def build_optimization_summary(result: ABCResult, *, runtime_mode: str, version: str) -> dict[str, object]:
    return {
        'optimization_version': version,
        'feature_weights': result.feature_weights,
        'selected_features': list(result.feature_weights.keys()),
        'class_balance_report': {
            'strategy': 'kmeanssmote',
            'false_negative_penalty': 4,
        },
        'abc_enabled': True,
        'abc_iterations': result.iterations,
        'abc_population_size': result.population_size,
        'holdout_pss': result.holdout_pss,
        'holdout_threshold': result.holdout_threshold,
        'runtime_mode': runtime_mode,
        'origin': result.origin,
        'generated_at': pd.Timestamp.now(tz='UTC').isoformat(),
    }
