from __future__ import annotations

import unittest

from backend.common.european_shadow_sources import (
    BENCHMARK_ROLE,
    FEATURE_JOIN_ROLE,
    PRODUCTION_SCORING_ROLE,
    SHADOW_TRAINING_ROLE,
    STAGING_ROLE,
    build_european_shadow_manifest,
    build_sar_training_manifest_from_staged_records,
    dataset_family_assessments,
    european_source_registry,
    normalize_staged_european_record,
    source_usage_issues,
    summarize_dataset_family_assessments,
)


class EuropeanShadowSourceTests(unittest.TestCase):
    def test_registry_contains_priority_european_sources_without_production_roles(self) -> None:
        registry = european_source_registry()

        expected = {
            'swiss_spot6_2018',
            'swiss_spot6_2019',
            'french_epa_historical',
            'french_clpa_extent_priors',
            'norway_sar_fcn_labels',
            'avalcd_zenodo_v1',
            'hiaval_hma',
            'everest_sentinel1',
            'bipad_nepal_avalanche_candidate',
            'slf_accident_datasets',
            'slf_data_service_weather_snowpack',
            'slf_bulletin_caaml',
        }
        self.assertTrue(expected.issubset(registry))
        for source in registry.values():
            self.assertNotIn(PRODUCTION_SCORING_ROLE, source.allowed_roles)
            self.assertTrue(source.risk_notes)

    def test_everest_sentinel_source_remains_benchmark_only_until_interval_join_exists(self) -> None:
        source = european_source_registry()['everest_sentinel1']

        self.assertEqual(source.data_lane, 'sar_detection_activity')
        self.assertEqual(source.default_training_role, BENCHMARK_ROLE)
        self.assertEqual(
            source_usage_issues(
                source,
                requested_role=SHADOW_TRAINING_ROLE,
                license_review_id='license-review-everest',
            ),
            ['source "everest_sentinel1" does not allow role "shadow_training"'],
        )

    def test_hiaval_is_permissive_reviewed_candidate_but_not_production(self) -> None:
        source = european_source_registry()['hiaval_hma']
        self.assertEqual(source.license, 'CC BY 4.0; preserve attribution and source references')
        self.assertNotIn(PRODUCTION_SCORING_ROLE, source.allowed_roles)
        issues = source_usage_issues(
            source,
            requested_role=SHADOW_TRAINING_ROLE,
            license_review_id='license-review-hiaval',
        )
        self.assertEqual(issues, [])

    def test_bipad_candidate_remains_benchmark_only_until_rights_review(self) -> None:
        source = european_source_registry()['bipad_nepal_avalanche_candidate']

        self.assertEqual(source.default_training_role, BENCHMARK_ROLE)
        issues = source_usage_issues(
            source,
            requested_role=SHADOW_TRAINING_ROLE,
            license_review_id='pending-bipad-review',
        )
        self.assertTrue(any('does not allow role' in issue for issue in issues))

    def test_manifest_summarizes_known_record_counts_by_lane(self) -> None:
        manifest = build_european_shadow_manifest(selected_keys=[
            'swiss_spot6_2018',
            'swiss_spot6_2019',
            'french_epa_historical',
            'norway_sar_fcn_labels',
            'norway_sar_activity_monitoring',
            'slf_data_service_weather_snowpack',
        ])

        self.assertEqual(manifest['version'], 'european_shadow_manifest_v1')
        occurrence = manifest['summary_by_lane']['occurrence_labels']
        sar = manifest['summary_by_lane']['sar_masks']
        weather = manifest['summary_by_lane']['weather_snowpack_features']

        self.assertEqual(occurrence['known_record_count'], 18737 + 6041 + 54641)
        self.assertEqual(sar['known_record_count'], 6345)
        self.assertEqual(manifest['summary_by_lane']['sar_detection_activity']['known_record_count'], 472000)
        self.assertEqual(weather['known_record_count'], 0)
        self.assertIn('slf_data_service_weather_snowpack', weather['unknown_record_count_sources'])
        self.assertEqual(manifest['dataset_family_summary']['family_count'], 4)
        self.assertEqual(manifest['dataset_family_summary']['highest_enhancement_value'], 5.0)

    def test_license_gate_blocks_shadow_training_until_reviewed(self) -> None:
        source = european_source_registry()['swiss_spot6_2018']

        issues = source_usage_issues(source, requested_role=SHADOW_TRAINING_ROLE)
        self.assertTrue(any('license_review_id' in issue for issue in issues))

        staged = normalize_staged_european_record({
            'source_key': 'swiss_spot6_2018',
            'external_id': 'spot6-2018-0001',
            'region_key': 'swiss_alps',
            'geometry_ref': 'local/staging/spot6_2018/0001.geojson',
        })
        self.assertEqual(staged['requested_role'], STAGING_ROLE)
        self.assertFalse(staged['training_eligible'])
        self.assertFalse(staged['production_eligible'])

        reviewed = normalize_staged_european_record({
            'source_key': 'swiss_spot6_2018',
            'external_id': 'spot6-2018-0001',
            'region_key': 'swiss_alps',
            'geometry_ref': 'local/staging/spot6_2018/0001.geojson',
            'license_review_id': 'license-review-spot6-2026-05-16',
        }, requested_role=SHADOW_TRAINING_ROLE)
        self.assertTrue(reviewed['training_eligible'])
        self.assertFalse(reviewed['production_eligible'])
        self.assertLessEqual(reviewed['training_weight'], 0.75)

    def test_context_and_feature_sources_do_not_enter_direct_shadow_training(self) -> None:
        registry = european_source_registry()

        bulletin_issues = source_usage_issues(
            registry['eaws_bulletin_context'],
            requested_role=SHADOW_TRAINING_ROLE,
            license_review_id='reviewed',
        )
        self.assertTrue(any('does not allow role' in issue for issue in bulletin_issues))

        weather_issues = source_usage_issues(
            registry['slf_data_service_weather_snowpack'],
            requested_role=FEATURE_JOIN_ROLE,
            license_review_id='reviewed',
        )
        self.assertEqual(weather_issues, [])

    def test_production_scoring_is_blocked_even_with_license_review(self) -> None:
        source = european_source_registry()['french_epa_historical']

        issues = source_usage_issues(
            source,
            requested_role=PRODUCTION_SCORING_ROLE,
            license_review_id='license-review-french-epa',
        )

        self.assertTrue(any('blocked from production scoring' in issue for issue in issues))

    def test_unknown_source_and_wrong_region_are_rejected(self) -> None:
        with self.assertRaises(KeyError):
            normalize_staged_european_record({
                'source_key': 'not-real',
                'external_id': 'x',
                'region_key': 'swiss_alps',
            })

        with self.assertRaisesRegex(ValueError, 'not allowed for source'):
            normalize_staged_european_record({
                'source_key': 'swiss_spot6_2018',
                'external_id': 'x',
                'region_key': 'french_alps',
            })

    def test_avalcd_staged_records_convert_to_existing_sar_manifest_contract(self) -> None:
        record = normalize_staged_european_record({
            'source_key': 'avalcd_zenodo_v1',
            'external_id': 'avalcd-scene-001',
            'event_id': 'avalcd-event-001',
            'scene_id': 'avalcd-scene-001',
            'region_key': 'scandinavia_norway',
            'stack_ref': 'staging/avalcd/scene001/stack_manifest.json',
            'truth_mask_ref': 'staging/avalcd/scene001/truth_mask.tif',
            'license_review_id': 'license-review-avalcd',
        }, requested_role=SHADOW_TRAINING_ROLE)

        manifest = build_sar_training_manifest_from_staged_records(
            [record],
            dataset_version='european-shadow-sar-test',
            split='val',
        )

        self.assertEqual(manifest['version'], 'sar_training_manifest_v1')
        self.assertEqual(manifest['dataset_version'], 'european-shadow-sar-test')
        self.assertEqual(manifest['scenes'][0]['source_dataset'], 'avalcd_zenodo_v1')
        self.assertEqual(manifest['scenes'][0]['split'], 'val')
        self.assertEqual(manifest['scenes'][0]['stack_ref'], 'staging/avalcd/scene001/stack_manifest.json')
        self.assertFalse(manifest['scenes'][0]['metadata']['production_eligible'])

    def test_non_sar_records_do_not_convert_to_sar_manifest(self) -> None:
        record = normalize_staged_european_record({
            'source_key': 'french_epa_historical',
            'external_id': 'epa-event-1',
            'region_key': 'french_alps',
            'license_review_id': 'license-review-french-epa',
        }, requested_role=SHADOW_TRAINING_ROLE)

        with self.assertRaisesRegex(ValueError, 'cannot build a SAR training scene'):
            build_sar_training_manifest_from_staged_records([record])

    def test_manifest_usage_gates_reflect_license_reviews(self) -> None:
        no_review = build_european_shadow_manifest(selected_keys=['swiss_spot6_2019'])
        reviewed = build_european_shadow_manifest(
            selected_keys=['swiss_spot6_2019'],
            license_review_ids={'swiss_spot6_2019': 'license-review-spot6-2019'},
        )

        self.assertFalse(no_review['usage_gates']['swiss_spot6_2019'][SHADOW_TRAINING_ROLE]['allowed'])
        self.assertTrue(reviewed['usage_gates']['swiss_spot6_2019'][SHADOW_TRAINING_ROLE]['allowed'])
        self.assertFalse(reviewed['usage_gates']['swiss_spot6_2019'][PRODUCTION_SCORING_ROLE]['allowed'])

    def test_benchmark_role_is_allowed_for_bulletin_labels_after_review(self) -> None:
        source = european_source_registry()['slf_bulletin_caaml']

        issues = source_usage_issues(
            source,
            requested_role=BENCHMARK_ROLE,
            license_review_id='license-review-slf-caaml',
        )

        self.assertEqual(issues, [])

    def test_updated_recommendation_dataset_family_assessments_are_manifested(self) -> None:
        assessments = dataset_family_assessments()

        self.assertEqual(len(assessments), 7)
        self.assertEqual(assessments['norway_472k_sar_detections'].enhancement_value, 5.0)
        self.assertEqual(assessments['swiss_spot6_24778_outlines'].enhancement_value, 4.5)
        self.assertEqual(assessments['french_epa_clpa'].enhancement_value, 4.5)
        self.assertEqual(assessments['swiss_weather_snowpack_danger'].enhancement_value, 4.0)
        self.assertEqual(assessments['avalcd'].enhancement_value, 4.0)
        self.assertEqual(assessments['slf_accident_datasets'].enhancement_value, 3.0)
        self.assertEqual(assessments['eaws_slf_bulletins'].enhancement_value, 2.5)

        summary = summarize_dataset_family_assessments(assessments.values())
        self.assertEqual(summary['family_count'], 7)
        self.assertEqual(summary['high_value_family_count'], 5)
        self.assertEqual(summary['average_enhancement_value'], 3.93)

    def test_slf_accident_dataset_is_benchmark_only_not_direct_shadow_training(self) -> None:
        source = european_source_registry()['slf_accident_datasets']

        benchmark_issues = source_usage_issues(
            source,
            requested_role=BENCHMARK_ROLE,
            license_review_id='license-review-slf-accidents',
        )
        shadow_issues = source_usage_issues(
            source,
            requested_role=SHADOW_TRAINING_ROLE,
            license_review_id='license-review-slf-accidents',
        )

        self.assertEqual(benchmark_issues, [])
        self.assertTrue(any('does not allow role' in issue for issue in shadow_issues))


if __name__ == '__main__':
    unittest.main()
