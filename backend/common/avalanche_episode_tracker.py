"""Deterministic, provenance-aware avalanche episode tracking.

This module tracks model-derived avalanche-problem episodes across forecast
cycles. It deliberately does not convert missing observations into negative
labels and never emits an official warning. A ``cell_id`` is the stable
spatial-overlap key supplied by the forecast-zone geometry contract; geometric
overlap calculation belongs to the upstream spatial adapter.
"""
from __future__ import annotations

import hashlib
import json
import math
from dataclasses import asdict, dataclass, replace
from datetime import datetime, timedelta, timezone
from typing import Any

from backend.common.snowpack_contracts import (
    AvalancheEpisodeContract,
    ContractValidationError,
)


_PROBLEM_TYPES = frozenset({
    'storm_slab',
    'wind_slab',
    'persistent_weak_layer',
    'wet_snow',
})
_EVIDENCE_STATES = frozenset({'model', 'observed_event', 'unknown', 'not_observed'})
_UPDATE_STATES = frozenset({'started', 'active', 'degrading', 'expired', 'unknown', 'observed_event'})


def _finite_number(value: object) -> bool:
    return (
        isinstance(value, (int, float))
        and not isinstance(value, bool)
        and math.isfinite(float(value))
    )


def _parse_utc(value: object, *, field: str) -> datetime:
    if not isinstance(value, str) or not value:
        raise ValueError(f'{field} must be a non-empty timestamp')
    try:
        parsed = datetime.fromisoformat(value.replace('Z', '+00:00'))
    except ValueError as exc:
        raise ValueError(f'{field} is not valid ISO-8601: {value!r}') from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError(f'{field} must be timezone-aware UTC')
    if parsed.utcoffset() != timedelta(0):
        raise ValueError(f'{field} must use UTC offset +00:00')
    return parsed.astimezone(timezone.utc)


@dataclass(frozen=True)
class EpisodeTrackerConfig:
    """Versioned thresholds for deterministic episode hysteresis."""

    config_version: str = 'episode_tracker_v1'
    start_probability: float = 0.60
    maintain_probability: float = 0.40
    minimum_confidence: float = 0.30
    minimum_coverage: float = 0.30
    start_persistence_cycles: int = 2
    expiry_cycles: int = 2
    expected_decay_h: int = 24

    def validate(self) -> None:
        if not isinstance(self.config_version, str) or not self.config_version.strip():
            raise ValueError('config_version is required')
        for field_name, value in (
            ('start_probability', self.start_probability),
            ('maintain_probability', self.maintain_probability),
            ('minimum_confidence', self.minimum_confidence),
            ('minimum_coverage', self.minimum_coverage),
        ):
            if not _finite_number(value) or not 0.0 <= float(value) <= 1.0:
                raise ValueError(f'{field_name} must be a finite number from 0 to 1')
        if not 0.0 <= self.maintain_probability <= self.start_probability <= 1.0:
            raise ValueError('maintain_probability <= start_probability and both must be 0-1')
        if type(self.start_persistence_cycles) is not int or self.start_persistence_cycles < 1:
            raise ValueError('start_persistence_cycles must be >= 1')
        if type(self.expiry_cycles) is not int or self.expiry_cycles < 1:
            raise ValueError('expiry_cycles must be >= 1')
        if type(self.expected_decay_h) is not int or self.expected_decay_h < 1:
            raise ValueError('expected_decay_h must be >= 1')


@dataclass(frozen=True)
class EpisodeObservation:
    """One forecast-cycle signal or independent observation state."""

    observation_id: str
    cycle_id: str
    observed_at: str
    cell_id: str
    region_key: str
    elevation_band: str
    aspect_class: str
    problem_type: str
    probability: float
    confidence: float
    coverage: float
    source_members: tuple[str, ...] = ()
    evidence_state: str = 'model'

    def validate(self) -> datetime:
        for field in (
            'observation_id', 'cycle_id', 'cell_id', 'region_key',
            'elevation_band', 'aspect_class',
        ):
            if not getattr(self, field):
                raise ValueError(f'{field} is required')
        if self.problem_type not in _PROBLEM_TYPES:
            raise ValueError(f'unsupported problem_type: {self.problem_type!r}')
        if self.evidence_state not in _EVIDENCE_STATES:
            raise ValueError(f'unsupported evidence_state: {self.evidence_state!r}')
        timestamp = _parse_utc(self.observed_at, field='observed_at')
        for field, value in (
            ('probability', self.probability),
            ('confidence', self.confidence),
            ('coverage', self.coverage),
        ):
            if not _finite_number(value) or not 0.0 <= float(value) <= 1.0:
                raise ValueError(f'{field} must be 0-1')
        if not all(isinstance(member, str) and member for member in self.source_members):
            raise ValueError('source_members must contain non-empty strings')
        return timestamp

    @property
    def key(self) -> tuple[str, str, str, str, str]:
        """Stable cell/problem key; upstream geometry defines cell overlap."""
        return (
            self.cell_id,
            self.region_key,
            self.elevation_band,
            self.aspect_class,
            self.problem_type,
        )


@dataclass(frozen=True)
class EpisodeUpdate:
    """Deterministic result of ingesting one observation."""

    update_state: str
    observation_id: str
    evidence_state: str
    episode: AvalancheEpisodeContract | None = None
    missing_cycles: int = 0
    official_warning_eligible: bool = False

    def validate(self) -> None:
        if self.update_state not in _UPDATE_STATES:
            raise ValueError(f'unsupported update_state: {self.update_state!r}')
        if self.evidence_state not in _EVIDENCE_STATES:
            raise ValueError(f'unsupported evidence_state: {self.evidence_state!r}')
        if self.missing_cycles < 0:
            raise ValueError('missing_cycles must be >= 0')
        if self.official_warning_eligible:
            raise ContractValidationError(
                'EpisodeUpdate cannot be official-warning eligible without Partner promotion'
            )
        if self.episode is not None:
            self.episode.validate()
            if self.episode.is_official_warning:
                raise ContractValidationError(
                    'EpisodeUpdate cannot contain an official warning episode'
                )

    def to_dict(self) -> dict[str, Any]:
        self.validate()
        payload = asdict(self)
        if self.episode is not None:
            payload['episode'] = asdict(self.episode)
        return payload


@dataclass
class _PendingEpisode:
    high_cycles: int
    first_detection: str
    last_observed_at: str


@dataclass
class _ActiveEpisode:
    episode: AvalancheEpisodeContract
    last_observed_at: str
    missing_cycles: int = 0


class AvalancheEpisodeTracker:
    """Stateful tracker with explicit hysteresis and missing-data semantics."""

    def __init__(self, config: EpisodeTrackerConfig | None = None) -> None:
        self.config = config or EpisodeTrackerConfig()
        self.config.validate()
        self._pending: dict[tuple[str, str, str, str, str], _PendingEpisode] = {}
        self._active: dict[tuple[str, str, str, str, str], _ActiveEpisode] = {}

    @staticmethod
    def _episode_id(key: tuple[str, ...], first_detection: str) -> str:
        digest = hashlib.sha256(
            ('|'.join(key) + '|' + first_detection).encode('utf-8')
        ).hexdigest()[:20]
        return f'episode-{digest}'

    @staticmethod
    def _copy_episode(
        episode: AvalancheEpisodeContract,
        *,
        observed_at: datetime,
        probability: float,
        confidence: float,
        coverage: float,
        source_members: tuple[str, ...],
    ) -> AvalancheEpisodeContract:
        first = _parse_utc(episode.first_detection, field='first_detection')
        persistence_h = max(0, int((observed_at - first).total_seconds() // 3600))
        return replace(
            episode,
            persistence_h=persistence_h,
            peak_probability=max(episode.peak_probability, probability),
            confidence=max(episode.confidence, confidence),
            coverage=max(episode.coverage, coverage),
            source_members=tuple(sorted(set(episode.source_members) | set(source_members))),
            is_official_warning=False,
        )

    def _quality_ok(self, observation: EpisodeObservation) -> bool:
        return (
            observation.confidence >= self.config.minimum_confidence
            and observation.coverage >= self.config.minimum_coverage
        )

    def ingest(self, observation: EpisodeObservation) -> EpisodeUpdate:
        observed_at = observation.validate()
        key = observation.key
        active = self._active.get(key)
        pending = self._pending.get(key)

        if active is not None and observed_at <= _parse_utc(
            active.last_observed_at, field='last_observed_at'
        ):
            raise ValueError('observations for an active key must be strictly chronological')
        if pending is not None and observed_at <= _parse_utc(
            pending.last_observed_at, field='last_observed_at'
        ):
            raise ValueError('observations for a pending key must be strictly chronological')

        if observation.evidence_state == 'observed_event':
            # Independent observed events are labels/validation inputs, not
            # model episodes. They must never create or promote an episode.
            update = EpisodeUpdate('observed_event', observation.observation_id, 'observed_event')
            update.validate()
            return update

        if observation.evidence_state in {'unknown', 'not_observed'}:
            if active is None:
                self._pending.pop(key, None)
                update = EpisodeUpdate('unknown', observation.observation_id, observation.evidence_state)
                update.validate()
                return update
            active.missing_cycles += 1
            if active.missing_cycles >= self.config.expiry_cycles:
                expired = active.episode
                self._active.pop(key, None)
                update = EpisodeUpdate(
                    'expired', observation.observation_id, observation.evidence_state,
                    episode=expired, missing_cycles=active.missing_cycles,
                )
            else:
                update = EpisodeUpdate(
                    'degrading', observation.observation_id, observation.evidence_state,
                    episode=active.episode, missing_cycles=active.missing_cycles,
                )
            update.validate()
            return update

        quality_ok = self._quality_ok(observation)
        if active is None:
            if not quality_ok or observation.probability < self.config.start_probability:
                self._pending.pop(key, None)
                update = EpisodeUpdate('unknown', observation.observation_id, 'model')
                update.validate()
                return update
            if pending is None:
                pending = _PendingEpisode(1, observation.observed_at, observation.observed_at)
            else:
                pending.high_cycles += 1
                pending.last_observed_at = observation.observed_at
            if pending.high_cycles < self.config.start_persistence_cycles:
                self._pending[key] = pending
                update = EpisodeUpdate('unknown', observation.observation_id, 'model')
                update.validate()
                return update

            episode = AvalancheEpisodeContract(
                episode_id=self._episode_id(key, pending.first_detection),
                problem_type=observation.problem_type,
                region_key=observation.region_key,
                elevation_band=observation.elevation_band,
                aspect_class=observation.aspect_class,
                first_detection=pending.first_detection,
                persistence_h=0,
                peak_probability=observation.probability,
                expected_decay_h=self.config.expected_decay_h,
                source_members=tuple(sorted(set(observation.source_members))),
                confidence=observation.confidence,
                coverage=observation.coverage,
                is_official_warning=False,
            )
            episode.validate()
            self._pending.pop(key, None)
            self._active[key] = _ActiveEpisode(episode, observation.observed_at)
            update = EpisodeUpdate('started', observation.observation_id, 'model', episode=episode)
            update.validate()
            return update

        if quality_ok and observation.probability >= self.config.maintain_probability:
            active.episode = self._copy_episode(
                active.episode,
                observed_at=observed_at,
                probability=observation.probability,
                confidence=observation.confidence,
                coverage=observation.coverage,
                source_members=observation.source_members,
            )
            active.last_observed_at = observation.observed_at
            active.missing_cycles = 0
            update = EpisodeUpdate('active', observation.observation_id, 'model', episode=active.episode)
        else:
            active.missing_cycles += 1
            if active.missing_cycles >= self.config.expiry_cycles:
                expired = active.episode
                self._active.pop(key, None)
                update = EpisodeUpdate(
                    'expired', observation.observation_id, 'model',
                    episode=expired, missing_cycles=active.missing_cycles,
                )
            else:
                update = EpisodeUpdate(
                    'degrading', observation.observation_id, 'model',
                    episode=active.episode, missing_cycles=active.missing_cycles,
                )
        update.validate()
        return update

    def to_dict(self) -> dict[str, Any]:
        """Serialize state for deterministic replay or durable job artifacts."""
        return {
            'schema_version': 'avalanche_episode_tracker_state_v1',
            'config': asdict(self.config),
            'pending': {
                '|'.join(key): asdict(value)
                for key, value in sorted(self._pending.items())
            },
            'active': {
                '|'.join(key): {
                    'episode': asdict(value.episode),
                    'last_observed_at': value.last_observed_at,
                    'missing_cycles': value.missing_cycles,
                }
                for key, value in sorted(self._active.items())
            },
        }

    def canonical_json(self) -> str:
        return json.dumps(self.to_dict(), sort_keys=True, separators=(',', ':'))

    @property
    def state_sha256(self) -> str:
        return hashlib.sha256(self.canonical_json().encode('utf-8')).hexdigest()

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> 'AvalancheEpisodeTracker':
        if not isinstance(payload, dict):
            raise ValueError('episode tracker state must be a JSON object')
        if payload.get('schema_version') != 'avalanche_episode_tracker_state_v1':
            raise ValueError('unsupported episode tracker state schema')
        raw_config = payload.get('config')
        raw_pending = payload.get('pending')
        raw_active = payload.get('active')
        if not isinstance(raw_config, dict):
            raise ValueError('episode tracker config must be an object')
        if not isinstance(raw_pending, dict) or not isinstance(raw_active, dict):
            raise ValueError('episode tracker pending and active state must be objects')
        try:
            config = EpisodeTrackerConfig(**raw_config)
        except (TypeError, ValueError) as exc:
            raise ValueError(f'invalid episode tracker config: {exc}') from exc
        tracker = cls(config)
        for raw_key, pending_state in raw_pending.items():
            if not isinstance(raw_key, str):
                raise ValueError('pending episode key must be a string')
            key = tuple(raw_key.split('|'))
            if len(key) != 5 or not all(key):
                raise ValueError('invalid pending episode state')
            if not isinstance(pending_state, dict):
                raise ValueError('pending episode state must be an object')
            try:
                pending = _PendingEpisode(**pending_state)
                if type(pending.high_cycles) is not int or pending.high_cycles < 1:
                    raise ValueError('pending high_cycles must be a positive integer')
                _parse_utc(pending.first_detection, field='pending.first_detection')
                _parse_utc(pending.last_observed_at, field='pending.last_observed_at')
            except (TypeError, KeyError, ValueError) as exc:
                raise ValueError(f'invalid pending episode state: {exc}') from exc
            tracker._pending[key] = pending
        for raw_key, active_state in raw_active.items():
            if not isinstance(raw_key, str):
                raise ValueError('active episode key must be a string')
            key = tuple(raw_key.split('|'))
            if len(key) != 5 or not all(key):
                raise ValueError('invalid active episode state')
            if not isinstance(active_state, dict):
                raise ValueError('active episode state must be an object')
            episode_data = active_state.get('episode')
            if not isinstance(episode_data, dict):
                raise ValueError('active episode state must contain an episode object')
            try:
                episode_data = dict(episode_data)
                episode_data['source_members'] = tuple(episode_data.get('source_members', ()))
                episode = AvalancheEpisodeContract(**episode_data)
                episode.validate()
                last_observed_at = active_state['last_observed_at']
                _parse_utc(last_observed_at, field='active.last_observed_at')
                missing_cycles = active_state.get('missing_cycles', 0)
                if type(missing_cycles) is not int or missing_cycles < 0:
                    raise ValueError('active missing_cycles must be a non-negative integer')
                if key[1:] != (
                    episode.region_key,
                    episode.elevation_band,
                    episode.aspect_class,
                    episode.problem_type,
                ):
                    raise ValueError('active episode key does not match episode context')
            except (ContractValidationError, KeyError, TypeError, ValueError) as exc:
                raise ValueError(f'invalid active episode state: {exc}') from exc
            tracker._active[key] = _ActiveEpisode(
                episode=episode,
                last_observed_at=last_observed_at,
                missing_cycles=missing_cycles,
            )
        return tracker
