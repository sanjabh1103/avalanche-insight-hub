"""Tests for deterministic avalanche episode tracking semantics."""
from __future__ import annotations

import unittest

from backend.common.avalanche_episode_tracker import (
    AvalancheEpisodeTracker,
    EpisodeObservation,
    EpisodeTrackerConfig,
)


def _obs(index: int, **overrides) -> EpisodeObservation:
    defaults = dict(
        observation_id=f'obs-{index}',
        cycle_id=f'cycle-{index}',
        observed_at=f'2026-01-15T0{index}:00:00+00:00',
        cell_id='cell-001',
        region_key='himalayas_nepal',
        elevation_band='middle',
        aspect_class='N',
        problem_type='wind_slab',
        probability=0.8,
        confidence=0.8,
        coverage=0.8,
        source_members=('member-01',),
        evidence_state='model',
    )
    defaults.update(overrides)
    return EpisodeObservation(**defaults)


class TestAvalancheEpisodeTracker(unittest.TestCase):
    def test_hysteresis_requires_two_high_cycles(self) -> None:
        tracker = AvalancheEpisodeTracker()
        self.assertEqual(tracker.ingest(_obs(1)).update_state, 'unknown')
        started = tracker.ingest(_obs(2))
        self.assertEqual(started.update_state, 'started')
        self.assertIsNotNone(started.episode)
        self.assertFalse(started.official_warning_eligible)

    def test_active_cycle_updates_peak_and_persistence(self) -> None:
        tracker = AvalancheEpisodeTracker()
        tracker.ingest(_obs(1))
        started = tracker.ingest(_obs(2))
        active = tracker.ingest(_obs(3, probability=0.95, source_members=('member-02',)))
        assert started.episode is not None
        assert active.episode is not None
        self.assertEqual(active.update_state, 'active')
        self.assertEqual(active.episode.peak_probability, 0.95)
        self.assertEqual(active.episode.source_members, ('member-01', 'member-02'))
        self.assertGreater(active.episode.persistence_h, 0)

    def test_low_signal_degrades_then_expires(self) -> None:
        tracker = AvalancheEpisodeTracker()
        tracker.ingest(_obs(1))
        tracker.ingest(_obs(2))
        self.assertEqual(tracker.ingest(_obs(3, probability=0.1)).update_state, 'degrading')
        expired = tracker.ingest(_obs(4, probability=0.1))
        self.assertEqual(expired.update_state, 'expired')
        self.assertIsNotNone(expired.episode)

    def test_unknown_and_not_observed_are_not_negative_labels(self) -> None:
        tracker = AvalancheEpisodeTracker()
        for state in ('unknown', 'not_observed'):
            result = tracker.ingest(_obs(1, evidence_state=state))
            self.assertEqual(result.update_state, 'unknown')
            self.assertEqual(result.evidence_state, state)
            self.assertIsNone(result.episode)

    def test_observed_event_is_validation_input_not_model_episode(self) -> None:
        tracker = AvalancheEpisodeTracker()
        result = tracker.ingest(_obs(1, evidence_state='observed_event'))
        self.assertEqual(result.update_state, 'observed_event')
        self.assertIsNone(result.episode)

    def test_problem_and_cell_keys_are_separate(self) -> None:
        tracker = AvalancheEpisodeTracker()
        tracker.ingest(_obs(1))
        first = tracker.ingest(_obs(2))
        tracker.ingest(_obs(1, cell_id='cell-002', problem_type='wet_snow'))
        second = tracker.ingest(_obs(2, cell_id='cell-002', problem_type='wet_snow'))
        self.assertNotEqual(first.episode.episode_id, second.episode.episode_id)

    def test_out_of_order_active_observation_fails(self) -> None:
        tracker = AvalancheEpisodeTracker()
        tracker.ingest(_obs(1))
        tracker.ingest(_obs(2))
        with self.assertRaises(ValueError):
            tracker.ingest(_obs(1, observed_at='2026-01-15T01:30:00+00:00'))

    def test_state_round_trip_is_deterministic(self) -> None:
        tracker = AvalancheEpisodeTracker()
        tracker.ingest(_obs(1))
        tracker.ingest(_obs(2))
        restored = AvalancheEpisodeTracker.from_dict(tracker.to_dict())
        self.assertEqual(tracker.canonical_json(), restored.canonical_json())
        self.assertEqual(tracker.state_sha256, restored.state_sha256)

    def test_malformed_state_shapes_fail_closed(self) -> None:
        valid = AvalancheEpisodeTracker().to_dict()
        for field, value in (
            ('config', []),
            ('pending', []),
            ('active', []),
        ):
            malformed = dict(valid)
            malformed[field] = value
            with self.subTest(field=field), self.assertRaises(ValueError):
                AvalancheEpisodeTracker.from_dict(malformed)

    def test_malformed_active_state_timestamp_fails_closed(self) -> None:
        tracker = AvalancheEpisodeTracker()
        tracker.ingest(_obs(1))
        tracker.ingest(_obs(2))
        payload = tracker.to_dict()
        active_key = next(iter(payload['active']))
        payload['active'][active_key]['last_observed_at'] = '2026-01-15T02:00:00'
        with self.assertRaises(ValueError):
            AvalancheEpisodeTracker.from_dict(payload)

    def test_config_rejects_inverted_thresholds(self) -> None:
        with self.assertRaises(ValueError):
            AvalancheEpisodeTracker(EpisodeTrackerConfig(start_probability=0.2, maintain_probability=0.3))

    def test_non_numeric_config_fails_closed(self) -> None:
        with self.assertRaises(ValueError):
            AvalancheEpisodeTracker(EpisodeTrackerConfig(start_probability='0.6'))  # type: ignore[arg-type]

    def test_non_numeric_observation_probability_fails_closed(self) -> None:
        with self.assertRaises(ValueError):
            _obs(1, probability='0.8').validate()  # type: ignore[arg-type]

    def test_official_warning_is_structurally_impossible(self) -> None:
        tracker = AvalancheEpisodeTracker()
        tracker.ingest(_obs(1))
        result = tracker.ingest(_obs(2))
        self.assertFalse(result.official_warning_eligible)
        self.assertFalse(result.episode.is_official_warning)


if __name__ == '__main__':
    unittest.main()
