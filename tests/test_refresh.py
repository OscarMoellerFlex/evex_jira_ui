import json
import tempfile
import unittest
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import patch

import pandas as pd

with patch("jira.JIRA"):
    import desk_sync


class RefreshTests(unittest.TestCase):
    def setUp(self):
        self.start = datetime(2026, 9, 1, tzinfo=UTC)
        self.end = datetime(2026, 9, 10, tzinfo=UTC)
        self.old = pd.DataFrame(
            {
                "key": ["SDIPR-1", "SDAX-1"],
                "firma": ["IPRO", "Amparex"],
                "value": [1, 2],
            }
        )

    @staticmethod
    def transform(project, issues):
        return pd.DataFrame(
            [
                {
                    "key": i["key"],
                    "firma": {"SDIPR": "IPRO", "SDAX": "Amparex", "SDEU": "Euronet"}[
                        project
                    ],
                    "value": 3,
                }
                for i in issues
            ]
        )

    def test_partial_failure_keeps_failed_desk_and_raw_snapshot(self):
        def fetch(start, end, **kw):
            if kw["project"] == "SDAX":
                raise RuntimeError("denied")
            return [{"key": kw["project"] + "-1"}]

        with tempfile.TemporaryDirectory() as tmp:
            raw = Path(tmp) / "raw.json"
            raw.write_text('["previous"]')
            result = desk_sync.refresh_desks(
                self.old,
                self.start,
                self.end,
                fetch=fetch,
                transform=self.transform,
                raw_path=raw,
            )
            self.assertEqual(result.frame.set_index("key").loc["SDAX-1", "value"], 2)
            self.assertEqual(set(result.frame["key"]), {"SDIPR-1", "SDAX-1", "SDEU-1"})
            self.assertEqual(set(result.errors), {"SDAX"})
            self.assertEqual(json.loads(raw.read_text()), ["previous"])

    def test_all_success_saves_combined_raw_and_accepts_zero_results(self):
        with tempfile.TemporaryDirectory() as tmp:
            raw = Path(tmp) / "raw.json"
            result = desk_sync.refresh_desks(
                None,
                self.start,
                self.end,
                fetch=lambda a, b, **k: (
                    [{"key": k["project"] + "-2"}] if k["project"] != "SDAX" else []
                ),
                transform=self.transform,
                raw_path=raw,
            )
            self.assertFalse(result.errors)
            self.assertEqual(result.counts, {"SDIPR": 1, "SDAX": 0, "SDEU": 1})
            self.assertEqual(
                [i["key"] for i in json.loads(raw.read_text())], ["SDIPR-2", "SDEU-2"]
            )

    def test_all_failure_preserves_entire_cache(self):
        def fetch(*args, **kwargs):
            raise RuntimeError("offline")

        result = desk_sync.refresh_desks(
            self.old,
            self.start,
            self.end,
            fetch=fetch,
            transform=self.transform,
            raw_path=None,
        )
        pd.testing.assert_frame_equal(result.frame, self.old)
        self.assertEqual(len(result.errors), 3)

    def test_enrichment_failures_are_reported_without_losing_tickets(self):
        result = desk_sync.refresh_desks(
            None,
            self.start,
            self.end,
            fetch=lambda a, b, **k: [
                {"key": k["project"] + "-1", "asset_errors": ["HTTP 403"]}
            ],
            transform=self.transform,
            raw_path=None,
        )
        self.assertEqual(len(result.frame), 3)
        self.assertEqual(result.asset_failures, {"SDIPR": 1, "SDAX": 1, "SDEU": 1})


if __name__ == "__main__":
    unittest.main()
