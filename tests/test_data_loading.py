import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import pandas as pd

import data_loading


class PersistenceTests(unittest.TestCase):
    def test_failed_serialization_keeps_previous_cache(self):
        with (
            tempfile.TemporaryDirectory() as tmp,
            patch.object(data_loading, "DATA_PATH", str(Path(tmp) / "cache.pkl")),
        ):
            data_loading.save_data(pd.DataFrame({"key": ["SDAX-1"]}))
            previous = Path(data_loading.DATA_PATH).read_bytes()
            with (
                patch.object(
                    data_loading.pickle,
                    "dump",
                    side_effect=RuntimeError("write failed"),
                ),
                self.assertRaises(RuntimeError),
            ):
                data_loading.save_data(pd.DataFrame())
            self.assertEqual(Path(data_loading.DATA_PATH).read_bytes(), previous)


if __name__ == "__main__":
    unittest.main()
