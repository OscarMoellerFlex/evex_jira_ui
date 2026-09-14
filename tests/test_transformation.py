import importlib
import json
import os
import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

import numpy as np
import pandas as pd


def issue(
    key="SDEU-1",
    *,
    main_id="main-1",
    sub_id="sub-1",
    request_status="Fertig",
    links=None,
    **top_level,
):
    raw = {
        "key": key,
        "fields": {
            "summary": "Printer cannot connect",
            "description": "Diagnostic text",
            "status": {"name": "Done", "statusCategory": {"name": "Done"}},
            "issuetype": {"name": "Service request"},
            "created": "2026-09-01T08:00:00.000+0000",
            "updated": "2026-09-01T12:00:00.000+0000",
            "labels": ["branch"],
            "priority": {"name": "High"},
            "customfield_10065": ["Support"],
            "customfield_10010": {
                "requestType": {"name": "Incident"},
                "currentStatus": {
                    "status": request_status,
                    "statusDate": {"jira": "2026-09-01T12:00:00.000+0000"},
                },
                "_links": {"agent": "https://jira.example/SDEU-1"},
            },
            "comment": {"comments": [{"body": "Investigating"}]},
            "customfield_10675": {"value": "Portal"},
            "customfield_10680": [] if main_id is None else [{"objectId": main_id}],
            "customfield_10679": [] if sub_id is None else [{"objectId": sub_id}],
            "customfield_10673": [{"objectId": "hq-1"}],
            "customfield_10674": [{"objectId": "branch-1"}],
            "issuelinks": links or [],
        },
    }
    raw.update(top_level)
    return raw


class TransformationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # Replace only the external client boundary; transformation stays real.
        os.environ.setdefault("JIRA_PASSWORD", "test-token")
        sys.modules.pop("data_transformation", None)
        with patch("jira.JIRA", return_value=MagicMock()):
            cls.transformation = importlib.import_module("data_transformation")
        fixture_path = Path(__file__).parent / "fixtures" / "legacy_transform.json"
        cls.legacy_golden = json.loads(fixture_path.read_text(encoding="utf-8"))

    def test_import_does_not_connect_to_jira(self):
        """Catches cached/offline transformation imports opening a Jira connection."""
        sys.modules.pop("data_transformation", None)
        with patch("jira.JIRA") as jira_constructor:
            importlib.import_module("data_transformation")
        jira_constructor.assert_not_called()

    def test_euronet_uses_amparex_fields_metrics_and_keeps_generic_links(self):
        """Catches SDEU using new field IDs or inheriting escalation flags."""
        linked = [{"type": {"name": "Relates"}, "outwardIssue": {"key": "EXAX-7"}}]
        raw = issue(
            links=linked,
            asset_labels={"main-1": "Hardware", "sub-1": "Printer"},
            assets_workspace_id="normal-workspace",
            assets_cloud_id="cloud-1",
            asset_errors=["main-2: HTTP 403"],
        )
        with patch.object(
            self.transformation, "load_clone_of_clone", return_value=("AX-9", "Cloners")
        ):
            row = self.transformation.load_issues_Euronet([raw]).iloc[0]

        self.assertEqual(row["firma"], "Euronet")
        self.assertEqual(row["request_type"], "Incident")
        self.assertEqual(row["source"], "Portal")
        self.assertEqual(row["Hauptkategorie"], "Hardware")
        self.assertEqual(row["Unterkategorie"], "Printer")
        self.assertEqual(row["clones"], "EXAX-7")
        self.assertEqual(row["clone_types"], "Relates")
        self.assertEqual(row["clones_of_clones"], "AX-9")
        self.assertTrue(bool(row["is_done"]))
        self.assertAlmostEqual(row["time_to_resolution_h"], 4.0)
        self.assertFalse(bool(row["has_exax_clone"]))
        self.assertFalse(bool(row["has_axt_clone_clone"]))
        self.assertEqual(row["assets_workspace_id"], "normal-workspace")
        self.assertEqual(row["assets_cloud_id"], "cloud-1")
        self.assertEqual(row["asset_errors"], "main-2: HTTP 403")

    def test_normal_assets_marker_blocks_stale_static_fallback(self):
        """Catches unresolved normal IDs being mislabeled by the legacy map."""
        raw = issue(
            asset_labels={},
            assets_workspace_id="normal-workspace",
            assets_cloud_id="cloud-1",
        )
        with patch.dict(
            self.transformation.object_id_to_name, {"main-1": "Stale sandbox label"}
        ):
            row = self.transformation.load_issues_Euronet([raw]).iloc[0]
        self.assertEqual(row["Hauptkategorie"], "Unbekannt")
        self.assertEqual(row["Unterkategorie"], "Unbekannt")

    def test_legacy_issue_uses_static_category_map(self):
        """Catches removal of the fallback for unenriched cached/raw issues."""
        with patch.dict(
            self.transformation.object_id_to_name,
            {"main-1": "Legacy main", "sub-1": "Legacy sub"},
        ):
            row = self.transformation.load_issues_Amparex([issue(key="SDAX-1")]).iloc[0]
        self.assertEqual(row["firma"], "Amparex")
        self.assertEqual(row["Hauptkategorie"], "Legacy main")
        self.assertEqual(row["Unterkategorie"], "Legacy sub")

    def test_cloned_by_keeps_first_link_semantics(self):
        """Catches later inward links changing the legacy first-link report."""
        links = [
            {"type": {"name": "Relates"}, "outwardIssue": {"key": "OTHER-1"}},
            {"type": {"name": "Cloners"}, "inwardIssue": {"key": "SOURCE-1"}},
        ]
        with patch.object(
            self.transformation, "load_clone_of_clone", return_value=("", "")
        ):
            row = self.transformation.load_issues_Amparex(
                [issue(key="SDAX-1", links=links)]
            ).iloc[0]
        self.assertEqual(row["cloned_by"], "")

    def test_old_desk_complete_fixtures_match_original_non_assets_behavior(self):
        """Catches shared-loader refactors changing established desk output."""
        links = [
            {
                "type": {"name": "Cloners"},
                "outwardIssue": {"key": "EXAX-7"},
                "inwardIssue": {"key": "SOURCE-1"},
            }
        ]
        cases = (
            ("load_issues", issue(key="SDIPR-1", links=links)),
            ("load_issues_Amparex", issue(key="SDAX-1", links=links)),
        )
        for loader_name, raw in cases:
            with (
                self.subTest(loader=loader_name),
                patch.object(
                    self.transformation,
                    "load_clone_of_clone",
                    return_value=("AX-9", "Cloners"),
                ),
            ):
                actual = getattr(self.transformation, loader_name)([raw])
            columns = self.legacy_golden["columns"]
            expected_row = self.legacy_golden["rows"][loader_name]
            expected_dtypes = self.legacy_golden["dtypes"]
            self.assertEqual(list(actual[columns].columns), columns)
            for column in columns:
                with self.subTest(loader=loader_name, column=column):
                    value = actual.iloc[0][column]
                    if isinstance(value, pd.Timestamp):
                        value = value.isoformat()
                    elif value is pd.NA or value is pd.NaT:
                        value = None
                    elif isinstance(value, np.generic):
                        value = value.item()
                    self.assertEqual(value, expected_row[column])
                    self.assertEqual(str(actual[column].dtype), expected_dtypes[column])

    def test_optional_nulls_and_empty_input_return_compatible_full_schema(self):
        """Catches optional fields crashing loaders or empty refreshes losing schema."""
        raw = issue(main_id=None, sub_id=None)
        raw["fields"].update(
            {
                "priority": None,
                "comment": None,
                "customfield_10010": None,
                "customfield_10065": None,
                "customfield_10675": None,
                "labels": None,
            }
        )
        row = self.transformation.load_issues_Euronet([raw]).iloc[0]
        empty = self.transformation.load_issues_Euronet([])

        self.assertEqual(row["priority"], "")
        self.assertEqual(row["comments"], "")
        self.assertEqual(row["request_type"], "")
        self.assertEqual(row["currentstatus_name"], "")
        self.assertEqual(row["category"], [])
        self.assertEqual(row["Hauptkategorie"], "Unbekannt")
        self.assertEqual(row["Unterkategorie"], "Unbekannt")
        self.assertTrue(empty.empty)
        self.assertEqual(
            list(empty.columns),
            list(self.transformation.load_issues_Amparex([]).columns),
        )
        self.assertTrue(
            str(empty["created"].dtype).startswith("datetime64[ns, Europe/Berlin]")
        )
        self.assertEqual(str(empty["is_done"].dtype), "boolean")
        self.assertEqual(empty["has_exax_clone"].dtype, bool)
        self.assertEqual(empty["has_axt_clone_clone"].dtype, bool)

    def test_project_dispatch_selects_the_configured_loader(self):
        """Catches a supported project being routed through the wrong company."""
        for project, expected_firma in (
            ("SDIPR", "IPRO"),
            ("SDAX", "Amparex"),
            ("SDEU", "Euronet"),
        ):
            with self.subTest(project=project):
                row = self.transformation.load_project_issues(
                    project, [issue(key=f"{project}-1")]
                ).iloc[0]
                self.assertEqual(row["firma"], expected_firma)

    def test_project_dispatch_rejects_unknown_project(self):
        """Catches silent misclassification of an unsupported project."""
        with self.assertRaisesRegex(ValueError, "UNKNOWN"):
            self.transformation.load_project_issues("UNKNOWN", [])

    def test_upsert_handles_empty_cache_duplicates_schema_and_explicit_nulls(self):
        """Catches duplicates, stale refreshed values, and unrelated-column loss."""
        old = pd.DataFrame(
            [
                {
                    "key": "A-1",
                    "summary": "older duplicate",
                    "priority": "Low",
                    "local_note": "discard",
                    "is_done": False,
                },
                {
                    "key": "A-1",
                    "summary": "old",
                    "priority": "High",
                    "local_note": "keep",
                    "is_done": False,
                },
            ]
        )
        new = pd.DataFrame(
            [
                {
                    "key": "A-1",
                    "summary": "intermediate",
                    "priority": "Medium",
                    "is_done": True,
                },
                {"key": "A-1", "summary": "new", "priority": None, "is_done": True},
                {
                    "key": "A-2",
                    "summary": "inserted",
                    "priority": "Low",
                    "is_done": False,
                },
            ]
        )
        result = self.transformation.upsert_jira_data(old, new).set_index("key")
        bootstrapped = self.transformation.upsert_jira_data(pd.DataFrame(), new)

        self.assertTrue(result.index.is_unique)
        self.assertEqual(result.loc["A-1", "summary"], "new")
        self.assertTrue(pd.isna(result.loc["A-1", "priority"]))
        self.assertEqual(result.loc["A-1", "local_note"], "keep")
        self.assertEqual(result["is_done"].dtype, bool)
        self.assertEqual(set(bootstrapped["key"]), {"A-1", "A-2"})
        self.assertTrue(bootstrapped["key"].is_unique)


if __name__ == "__main__":
    unittest.main()
