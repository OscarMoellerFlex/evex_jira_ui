"""Regression coverage for the multi-session DuckDB deadlock."""

import subprocess
import sys
import unittest
from pathlib import Path


class InteractiveConcurrencyTest(unittest.TestCase):
    def test_concurrent_renderers_complete(self):
        # Run real PyGWalker/DuckDB initialization in a separate process so a
        # regression holding the GIL cannot freeze the test runner itself.
        script = """
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch
import pandas as pd
from interactive import render_interactive

with patch('pygwalker.api.streamlit.init_streamlit_comm'), \\
     patch('pygwalker.api.pygwalker.check_update'), \\
     patch('pygwalker.api.streamlit.StreamlitRenderer.explorer') as explorer:
    with ThreadPoolExecutor(max_workers=4) as pool:
        futures = [
            pool.submit(render_interactive, pd.DataFrame({
                f'count_{i}': [i, i + 1], 'source': ['Email', 'Portal']
            }))
            for i in range(32)
        ]
        for future in futures:
            future.result()
    assert explorer.call_count == 32
"""
        result = subprocess.run(
            [sys.executable, "-c", script],
            cwd=Path(__file__).resolve().parents[1],
            capture_output=True,
            text=True,
            timeout=30,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)


if __name__ == "__main__":
    unittest.main()
