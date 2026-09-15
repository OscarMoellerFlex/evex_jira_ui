"""Regression tests for the resolution_band step of backfill_country."""

import pandas as pd

from backfill_country import BAND_COLUMN, add_resolution_band
from resolution_bands import BAND_NOT_DONE, BAND_UNDER_1H


def test_add_resolution_band_coerces_empty_strings_without_raising():
    # app.py's upsert fills columns missing on either side with "" (app.py:147-152),
    # so real data can hold a float/"" mix in an otherwise-numeric hours column.
    # A naive `<=` comparison against "" raises TypeError - add_resolution_band
    # must coerce before classifying, landing those rows in BAND_NOT_DONE.
    df = pd.DataFrame(
        {
            "time_to_resolution_biz_hours": [0.5, "", 20.0],
            "is_done": [True, True, True],
        }
    )

    out = add_resolution_band(df)

    assert list(out[BAND_COLUMN][:1]) == [BAND_UNDER_1H]
    assert out[BAND_COLUMN][1] == BAND_NOT_DONE


def test_add_resolution_band_warns_and_skips_when_column_missing(capsys):
    df = pd.DataFrame({"is_done": [True]})

    out = add_resolution_band(df)

    assert BAND_COLUMN not in out.columns
    captured = capsys.readouterr()
    assert "time_to_resolution_biz_hours" in captured.out
    assert "Länder tab" in captured.out
