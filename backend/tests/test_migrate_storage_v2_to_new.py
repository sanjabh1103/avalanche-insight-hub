from __future__ import annotations

import unittest
from unittest.mock import Mock, patch

from scripts import migrate_storage_v2_to_new


class TestStorageMigrationSourceBinding(unittest.TestCase):
    def test_inventory_preserves_nested_object_path(self) -> None:
        folder_responses = []
        for name in ("avalanche", "himalayas_nepal", "run-123"):
            response = Mock()
            response.status_code = 200
            response.json.return_value = [{"name": name, "id": None, "metadata": None}]
            folder_responses.append(response)
        file_response = Mock()
        file_response.status_code = 200
        file_response.json.return_value = [{
            "name": "manifest.json",
            "id": "object-id",
            "metadata": {"size": 12},
        }]

        with patch.object(
            migrate_storage_v2_to_new.requests,
            "post",
            side_effect=[*folder_responses, file_response],
        ):
            files = migrate_storage_v2_to_new.deep_list(
                "https://source.example",
                {"Authorization": "source"},
                "forecast-products",
            )

        self.assertEqual([item["name"] for item in files], [
            "avalanche/himalayas_nepal/run-123/manifest.json",
        ])

    def test_inventory_uses_explicit_source_parameters(self) -> None:
        response = Mock()
        response.status_code = 200
        response.json.return_value = [{
            "name": "run/manifest.json",
            "id": "object-id",
            "metadata": {"size": 12},
        }]

        with patch.object(migrate_storage_v2_to_new.requests, "post", return_value=response) as post:
            migrated, failed = migrate_storage_v2_to_new.migrate_bucket(
                "https://source.example",
                "https://target.example",
                {"Authorization": "source"},
                {"Authorization": "target"},
                "forecast-products",
                apply=False,
            )

        self.assertEqual((migrated, failed), (0, 0))
        self.assertEqual(post.call_args.args[0], "https://source.example/storage/v1/object/list/forecast-products")
        self.assertEqual(post.call_args.kwargs["headers"]["Authorization"], "source")

    def test_inventory_paginates_source_files(self) -> None:
        page_one = Mock()
        page_one.status_code = 200
        page_one.json.return_value = [
            {"name": f"run/{index:03d}.json", "id": f"id-{index}", "metadata": {"size": 1}}
            for index in range(100)
        ]
        page_two = Mock()
        page_two.status_code = 200
        page_two.json.return_value = [{"name": "run/100.json", "id": "id-100", "metadata": {"size": 1}}]

        with patch.object(
            migrate_storage_v2_to_new.requests,
            "post",
            side_effect=[page_one, page_two],
        ) as post:
            migrated, failed = migrate_storage_v2_to_new.migrate_bucket(
                "https://source.example",
                "https://target.example",
                {"Authorization": "source"},
                {"Authorization": "target"},
                "forecast-products",
                apply=False,
            )

        self.assertEqual((migrated, failed), (0, 0))
        self.assertEqual(post.call_count, 2)
        self.assertEqual(post.call_args_list[0].kwargs["json"]["offset"], 0)
        self.assertEqual(post.call_args_list[1].kwargs["json"]["offset"], 100)

    def test_inventory_fails_closed_on_listing_error(self) -> None:
        response = Mock()
        response.status_code = 503
        response.text = "temporarily unavailable"

        with patch.object(migrate_storage_v2_to_new.requests, "post", return_value=response):
            with self.assertRaisesRegex(RuntimeError, "Storage listing failed"):
                migrate_storage_v2_to_new.migrate_bucket(
                    "https://source.example",
                    "https://target.example",
                    {"Authorization": "source"},
                    {"Authorization": "target"},
                    "forecast-products",
                    apply=False,
                )


if __name__ == "__main__":
    unittest.main()
