import unittest
from unittest.mock import Mock, patch

import pandas as pd

from source_sync import fetch_issue_sources, refresh_missing_sources


class SourceSyncTest(unittest.TestCase):
    def test_refreshes_old_tickets_without_overwriting_existing_sources(self):
        df = pd.DataFrame(
            {
                "key": ["SDAX-1", "SDIPR-2", "SDAX-3", "SDIPR-4"],
                "source": ["", None, "Portal", "  "],
                "created": ["2025-01-01"] * 4,
            }
        )
        original = df.copy(deep=True)
        fetch = Mock(
            return_value={"SDAX-1": "Anruf", "SDIPR-2": "INTERN", "SDAX-3": "E-Mail"}
        )
        result, count = refresh_missing_sources(df, fetch)
        fetch.assert_called_once_with(["SDAX-1", "SDIPR-2", "SDIPR-4"])
        self.assertEqual(result.source.tolist(), ["Anruf", "INTERN", "Portal", "  "])
        self.assertEqual(count, 2)
        pd.testing.assert_frame_equal(df, original)

    def test_no_missing_sources_requires_no_network(self):
        fetch = Mock()
        _, count = refresh_missing_sources(
            pd.DataFrame({"key": ["SDAX-1"], "source": ["E-Mail"]}), fetch
        )
        self.assertEqual(count, 0)
        fetch.assert_not_called()

    def test_read_paginates_without_a_creation_date_filter(self):
        with patch("source_sync.load_dotenv"), patch.dict(
            "os.environ",
            {
                "JIRA_URL": "https://example.atlassian.net",
                "JIRA_USERNAME": "test",
                "JIRA_PASSWORD": "test",
            },
        ), patch("source_sync.requests.Session") as session:
            first = Mock()
            first.json.return_value = {
                "issues": [
                    {
                        "key": "SDAX-1",
                        "fields": {"customfield_10675": {"value": "Anruf"}},
                    }
                ],
                "nextPageToken": "next",
            }
            second = Mock()
            second.json.return_value = {
                "issues": [{"key": "SDIPR-2", "fields": {"customfield_10675": None}}],
                "isLast": True,
            }
            client = session.return_value.__enter__.return_value
            client.post.side_effect = [first, second]
            self.assertEqual(
                fetch_issue_sources(["SDAX-1", "SDIPR-2"]),
                {"SDAX-1": "Anruf", "SDIPR-2": ""},
            )
            self.assertEqual(client.post.call_count, 2)
            self.assertNotIn("created", client.post.call_args.kwargs["json"]["jql"])
            self.assertEqual(
                client.post.call_args.kwargs["json"]["nextPageToken"], "next"
            )

    def test_fetch_failure_does_not_change_cache_data(self):
        df = pd.DataFrame({"key": ["SDAX-1"], "source": [""]})
        original = df.copy(deep=True)
        with self.assertRaises(RuntimeError):
            refresh_missing_sources(
                df, Mock(side_effect=RuntimeError("Jira unavailable"))
            )
        pd.testing.assert_frame_equal(df, original)
