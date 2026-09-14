import unittest
from unittest.mock import patch

import pandas as pd
from streamlit.testing.v1 import AppTest


class CompanyUITests(unittest.TestCase):
    def test_company_selector_defaults_all_and_empty_selection_stops_cleanly(self):
        with patch("data_loading.load_data", return_value=pd.DataFrame()):
            app = AppTest.from_file("app.py", default_timeout=30).run()
            self.assertEqual(len(app.multiselect), 1)
            self.assertEqual(app.multiselect[0].value, ["Ipro", "Amparex", "Euronet"])
            app.multiselect[0].set_value([]).run()
            self.assertFalse(app.exception)
            self.assertTrue(any("Firma" in info.value for info in app.info))

    def test_selected_companies_reach_raw_data_and_empty_optional_charts_render(self):
        from datetime import date

        from test_transformation import issue

        from data_transformation import load_project_issues

        frames = []
        for project in ["SDIPR", "SDAX", "SDEU"]:
            raw = issue(key=project + "-1", main_id=None, sub_id=None)
            raw["fields"]["customfield_10010"] = None
            raw["fields"]["customfield_10675"] = None
            frames.append(load_project_issues(project, [raw]))
        frame = pd.concat(frames, ignore_index=True)
        frame["category_asset_errors"] = ["HTTP 403", "", ""]
        with (
            patch("data_loading.load_data", return_value=frame),
            patch("interactive.render_interactive"),
        ):
            app = AppTest.from_file("app.py", default_timeout=30).run()
            app.sidebar.date_input[0].set_value(
                (date(2026, 9, 1), date(2026, 9, 10))
            ).run()
            self.assertFalse(app.exception)
            raw_frame = app.dataframe[0].value
            self.assertEqual(set(raw_frame["key"]), {"SDIPR-1", "SDAX-1", "SDEU-1"})
            self.assertTrue(any("Assets" in warning.value for warning in app.warning))
            app.multiselect[0].set_value(["Euronet", "Ipro"]).run()
            self.assertFalse(app.exception)
            self.assertEqual(set(app.dataframe[0].value["key"]), {"SDIPR-1", "SDEU-1"})


if __name__ == "__main__":
    unittest.main()
