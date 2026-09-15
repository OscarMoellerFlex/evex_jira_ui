import unittest

import pandas as pd

import asset_migration


class AssetMigrationTests(unittest.TestCase):
    def test_replaces_stale_labels_and_reports_denied_objects_without_dropping_rows(
        self,
    ):
        frame = pd.DataFrame(
            {
                "key": ["SDAX-1", "SDIPR-1"],
                "main_category_id": ["1", "1"],
                "sub_category_id": ["2", ""],
                "Hauptkategorie": ["sandbox", "sandbox"],
                "Unterkategorie": ["old", "old"],
                "summary": ["keep", "keep"],
                "has_exax_clone": [True, False],
            }
        )
        seen = []

        def fetch(cloud, workspace, oid):
            seen.append((cloud, workspace, oid))
            if oid == "2":
                raise PermissionError("denied")
            return {"id": oid, "label": "Normal category"}

        result, report = asset_migration.migrate_categories(frame, fetch=fetch)
        self.assertEqual(
            result["Hauptkategorie"].tolist(), ["Normal category", "Normal category"]
        )
        self.assertEqual(result["Unterkategorie"].tolist(), ["Unbekannt", "Unbekannt"])
        self.assertEqual(result["summary"].tolist(), ["keep", "keep"])
        self.assertEqual(result["has_exax_clone"].tolist(), [True, False])
        self.assertEqual(len(seen), 2)
        self.assertTrue(
            all(w == "9926cb30-3f07-4fb2-9c83-aa4fc551c721" for _, w, _ in seen)
        )
        self.assertEqual(report["failed_objects"], 1)
        self.assertIn("PermissionError", result.iloc[0]["category_asset_errors"])
        self.assertEqual(len(frame.columns), 7)

    def test_wrong_returned_identity_is_not_used(self):
        frame = pd.DataFrame(
            {"key": ["SDAX-1"], "main_category_id": ["1"], "sub_category_id": [""]}
        )
        result, report = asset_migration.migrate_categories(
            frame, fetch=lambda *a: {"id": "other", "label": "Wrong"}
        )
        self.assertEqual(result.iloc[0]["Hauptkategorie"], "Unbekannt")
        self.assertEqual(report["failed_objects"], 1)


if __name__ == "__main__":
    unittest.main()
