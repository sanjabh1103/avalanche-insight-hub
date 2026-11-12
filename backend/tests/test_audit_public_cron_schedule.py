import unittest
from textwrap import dedent

from scripts.audit_public_cron_schedule import build_audit_report


class PublicCronScheduleAuditTests(unittest.TestCase):
    def test_counts_frequency_maps_job_and_calculates_timeout_ceiling(self) -> None:
        workflow = """
        on:
          schedule:
            - cron: '0 3 * * *'  # daily cleanup
            - cron: '7 4 * * 1'  # weekly training
          workflow_dispatch:
        jobs:
          cleanup:
            if: github.event_name == 'schedule' && github.event.schedule == '0 3 * * *'
            runs-on: ubuntu-latest
            timeout-minutes: 15
          train:
            if: github.event_name == 'schedule' && github.event.schedule == '7 4 * * 1'
            runs-on: ubuntu-latest
            timeout-minutes: 60
        """

        report = build_audit_report(dedent(workflow))

        self.assertTrue(report["contract_ok"])
        self.assertEqual(report["active_trigger_count"], 2)
        self.assertEqual(report["daily_trigger_count"], 1)
        self.assertEqual(report["weekly_trigger_count"], 1)
        self.assertEqual(report["condition_count"], 2)
        self.assertEqual(report["triggers"][0]["job_ids"], ["cleanup"])
        self.assertEqual(report["triggers"][1]["job_ids"], ["train"])
        self.assertAlmostEqual(
            report["timeout_ceiling_minutes_month"],
            (365.2425 / 12 * 15) + (365.2425 / 7 / 12 * 60),
            places=1,
        )

    def test_comment_only_crons_are_not_active(self) -> None:
        workflow = """
        on:
          schedule:
            # - cron: '0 0 * * *'
            - cron: '0 3 * * *'
        jobs:
          cleanup:
            if: github.event.schedule == '0 3 * * *'
            timeout-minutes: 15
        """

        report = build_audit_report(dedent(workflow))

        self.assertEqual(report["active_trigger_count"], 1)
        self.assertEqual(report["triggers"][0]["cron"], "0 3 * * *")
        self.assertTrue(report["contract_ok"])


if __name__ == "__main__":
    unittest.main()
