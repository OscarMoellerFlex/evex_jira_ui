import itertools
import unittest
from datetime import UTC, datetime

import pandas as pd

import service_desks as desks


class DeskTests(unittest.TestCase):
    def test_every_company_subset_filters_without_cross_company_rows(self):
        frame = pd.DataFrame(
            {
                "firma": ["IPRO", "Amparex", "Euronet"],
                "key": ["SDIPR-1", "SDAX-1", "SDEU-1"],
            }
        )
        labels = ["Ipro", "Amparex", "Euronet"]
        keys = {"Ipro": "SDIPR-1", "Amparex": "SDAX-1", "Euronet": "SDEU-1"}
        for n in range(4):
            for selection in itertools.combinations(labels, n):
                with self.subTest(selection=selection):
                    self.assertEqual(
                        desks.filter_companies(frame, selection)["key"].tolist(),
                        [keys[x] for x in selection],
                    )

    def test_only_euronet_start_is_clamped_to_berlin_midnight(self):
        start = datetime(2025, 9, 1, tzinfo=UTC)
        self.assertEqual(
            desks.effective_start("SDEU", start).isoformat(),
            "2026-08-31T22:00:00+00:00",
        )
        self.assertEqual(desks.effective_start("SDAX", start), start)
        later = datetime(2026, 9, 3, tzinfo=UTC)
        self.assertEqual(desks.effective_start("SDEU", later), later)

    def test_import_filters_wrong_projects_and_pre_cutoff_records(self):
        issues = [
            {"key": "SDEU-1", "fields": {"created": "2026-08-31T21:59:59+00:00"}},
            {"key": "SDEU-2", "fields": {"created": "2026-08-31T22:00:00+00:00"}},
            {"key": "SDAX-3", "fields": {"created": "2026-09-02T00:00:00+00:00"}},
        ]
        result = desks.filter_issue_window(
            "SDEU",
            issues,
            datetime(2025, 1, 1, tzinfo=UTC),
            datetime(2026, 9, 10, tzinfo=UTC),
        )
        self.assertEqual([i["key"] for i in result], ["SDEU-2"])


if __name__ == "__main__":
    unittest.main()
