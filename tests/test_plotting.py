"""Stack-order tests for create_toggle_chart.

The resolution bands are a colour ramp (green -> yellow -> red -> grey), so
they only read correctly when stacked in BAND_ORDER. Left to groupby, the
order is alphabetical by label, which interleaves the ramp.
"""

import pandas as pd
import pytest

import plotting
from resolution_bands import BAND_ORDER


class _Ctx:
    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


class _Figure:
    """Absorbs any fig.*() call - we assert on px.bar's kwargs, not the figure."""

    def __getattr__(self, name):
        def accept(*args, **kwargs):
            return self

        return accept


@pytest.fixture
def captured(monkeypatch):
    """Render a chart against stubbed Streamlit/Plotly, return px.bar's kwargs."""
    seen = {}

    def fake_bar(*args, **kwargs):
        seen.update(kwargs)
        return _Figure()

    monkeypatch.setattr(plotting.px, "bar", fake_bar)
    monkeypatch.setattr(plotting.st, "radio", lambda *a, **k: plotting.MODE_ABS)
    monkeypatch.setattr(plotting.st, "plotly_chart", lambda *a, **k: None)
    monkeypatch.setattr(plotting.st, "columns", lambda *a, **k: (_Ctx(), _Ctx()))
    return seen


def _frame():
    # Deliberately built so alphabetical order != BAND_ORDER.
    rows = []
    for country in ("Deutschland", "Österreich"):
        for band in reversed(BAND_ORDER):
            rows.append({"Land": country, "resolution_band": band, "key": f"{band}-1"})
    return pd.DataFrame(rows)


def test_group_order_is_honoured(captured):
    plotting.create_toggle_chart(
        _frame(),
        x_col="Land",
        group_col="resolution_band",
        group_order=BAND_ORDER,
        toggle_key="t1",
    )
    assert captured["category_orders"]["resolution_band"] == BAND_ORDER


def test_without_group_order_the_stack_is_not_the_ramp(captured):
    """Documents why group_order exists - remove it and the ramp interleaves."""
    plotting.create_toggle_chart(
        _frame(), x_col="Land", group_col="resolution_band", toggle_key="t2"
    )
    assert captured["category_orders"]["resolution_band"] != BAND_ORDER


def test_labels_absent_from_the_data_are_not_charted(captured):
    df = _frame()
    df = df[df["resolution_band"] != BAND_ORDER[1]]

    plotting.create_toggle_chart(
        df,
        x_col="Land",
        group_col="resolution_band",
        group_order=BAND_ORDER,
        toggle_key="t3",
    )

    expected = [band for band in BAND_ORDER if band != BAND_ORDER[1]]
    assert captured["category_orders"]["resolution_band"] == expected


def test_unexpected_label_is_appended_not_dropped(captured):
    """An unknown band must still be charted, or its tickets vanish silently."""
    df = _frame()
    df.loc[0, "resolution_band"] = "Neue Kategorie"

    plotting.create_toggle_chart(
        df,
        x_col="Land",
        group_col="resolution_band",
        group_order=BAND_ORDER,
        toggle_key="t4",
    )

    order = captured["category_orders"]["resolution_band"]
    assert "Neue Kategorie" in order
    assert order[-1] == "Neue Kategorie"
