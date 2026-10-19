import unittest
from pathlib import Path

from scripts.verify_schedule_contract import extract_cron_triggers, extract_schedule_conditions


REPO_ROOT = Path(__file__).resolve().parents[2]


class ScheduleConditionParserTests(unittest.TestCase):
    def test_ignores_disabled_yaml_comment_conditions(self) -> None:
        workflow = """
        # if: github.event.schedule == 'disabled-cron'
        if: github.event.schedule == 'active-cron'
        """
        self.assertEqual(
            extract_schedule_conditions(workflow),
            ['active-cron'],
        )

    def test_private_workflow_uses_public_schedule_template(self) -> None:
        private_workflow = (REPO_ROOT / '.github/workflows/ml_pipeline.yml').read_text(encoding='utf-8')
        public_template = (REPO_ROOT / 'config/public_cron_schedule.yml').read_text(encoding='utf-8')

        self.assertEqual(extract_cron_triggers(private_workflow), set())
        self.assertEqual(len(extract_cron_triggers(public_template)), 9)
        self.assertIn('config/public_cron_schedule.yml', (REPO_ROOT / 'scripts/sync_to_public.sh').read_text(encoding='utf-8'))


if __name__ == '__main__':
    unittest.main()
