"""Resolution-time bands for the Länder tab.

Pure classification: business hours in, band label out. This lives outside
data_transformation.py on purpose - that module builds a live JIRA client at
import time, so anything defined there cannot be imported without credentials
and therefore cannot be tested.
"""

import pandas as pd

BAND_UNDER_1H = "≤ 1 Stunde"
BAND_UNDER_1D = "≤ 1 Arbeitstag"
BAND_OVER_1D = "> 1 Arbeitstag"
BAND_NOT_DONE = "Nicht abgeschlossen"

BAND_ORDER = [BAND_UNDER_1H, BAND_UNDER_1D, BAND_OVER_1D, BAND_NOT_DONE]

BAND_COLORS = {
    BAND_UNDER_1H: "green",
    BAND_UNDER_1D: "#FFD700",
    BAND_OVER_1D: "#D62728",
    BAND_NOT_DONE: "#9E9E9E",
}

ONE_HOUR = 1.0

# The dashboard's business window is 08:00-18:00 (BUS_START/BUS_END in
# data_transformation.py), so one working day is ten business hours.
HOURS_PER_WORKING_DAY = 10.0


def classify_band(biz_hours, is_done, hours_per_working_day=HOURS_PER_WORKING_DAY):
    """Return the resolution band label for a single ticket."""
    if not is_done:
        return BAND_NOT_DONE
    if biz_hours is None or pd.isna(biz_hours):
        # Defensive: a done ticket should always carry business hours.
        return BAND_NOT_DONE
    if biz_hours <= ONE_HOUR:
        return BAND_UNDER_1H
    if biz_hours <= hours_per_working_day:
        return BAND_UNDER_1D
    return BAND_OVER_1D


def classify_bands(biz_hours, is_done, hours_per_working_day=HOURS_PER_WORKING_DAY):
    """Vectorised classify_band: two Series in, a Series of labels out."""
    hours = pd.Series(biz_hours)
    done = pd.Series(is_done).fillna(False).astype(bool)

    # Widest band first, then narrow - each assignment overwrites the last.
    bands = pd.Series(BAND_OVER_1D, index=hours.index, dtype="object")
    bands[hours <= hours_per_working_day] = BAND_UNDER_1D
    bands[hours <= ONE_HOUR] = BAND_UNDER_1H
    # NaN comparisons above are False, so unresolved rows land here.
    bands[hours.isna() | ~done] = BAND_NOT_DONE
    return bands
