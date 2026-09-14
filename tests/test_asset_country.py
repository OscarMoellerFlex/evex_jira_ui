"""Escalation, bucket and cache tests for asset_country."""

import json

import pandas as pd

from asset_country import (
    NO_ASSETS_LINKED,
    NO_COUNTRY_ON_ASSET,
    NO_SOURCE,
    attach_country,
    classify_country,
    load_cache,
    normalise_object_id,
    resolve_missing,
    save_cache,
)

CACHE = {"1": "Deutschland", "2": "Österreich", "3": None}


def test_ansprechpartner_wins_over_filiale_and_zentrale():
    assert classify_country("ID_2", "ID_1", "ID_1", CACHE) == (
        "Österreich",
        "ansprechpartner",
    )


def test_falls_through_to_filiale_when_ansprechpartner_has_no_land():
    assert classify_country("ID_3", "ID_1", None, CACHE) == ("Deutschland", "filiale")


def test_falls_through_to_zentrale():
    assert classify_country("", "", "ID_2", CACHE) == ("Österreich", "zentrale")


def test_no_assets_at_all():
    assert classify_country("", "", "", CACHE) == (NO_ASSETS_LINKED, NO_SOURCE)


def test_assets_present_but_none_carry_land():
    assert classify_country("ID_3", "ID_3", "ID_3", CACHE) == (
        NO_COUNTRY_ON_ASSET,
        NO_SOURCE,
    )


def test_unknown_id_is_an_asset_without_land():
    assert classify_country("ID_999", "", "", CACHE) == (NO_COUNTRY_ON_ASSET, NO_SOURCE)


def test_normalise_strips_prefix_and_detects_absence():
    assert normalise_object_id("ID_42") == "42"
    assert normalise_object_id("42") == "42"
    assert normalise_object_id("") is None
    assert normalise_object_id("nan") is None
    assert normalise_object_id("None") is None
    assert normalise_object_id(None) is None
    assert normalise_object_id(float("nan")) is None


def test_attach_country_adds_columns_without_mutating():
    df = pd.DataFrame(
        {
            "key": ["A-1", "A-2", "A-3"],
            "ansprechpartner": ["", "ID_3", ""],
            "filiale": ["", "", ""],
            "zentrale": ["ID_1", "", ""],
        }
    )
    before = df.copy()
    out = attach_country(df, CACHE)
    pd.testing.assert_frame_equal(df, before)
    assert list(out["Land"]) == ["Deutschland", NO_COUNTRY_ON_ASSET, NO_ASSETS_LINKED]
    assert list(out["land_quelle"]) == ["zentrale", NO_SOURCE, NO_SOURCE]


def test_attach_country_tolerates_missing_column():
    df = pd.DataFrame({"key": ["A-1"], "zentrale": ["ID_1"], "filiale": [""]})
    out = attach_country(df, CACHE)
    assert list(out["Land"]) == ["Deutschland"]


def test_resolve_missing_only_fetches_unknown_ids():
    calls = []

    def fake(object_id):
        calls.append(object_id)
        return "Schweiz"

    cache = {"1": "Deutschland"}
    cache, resolved, failed = resolve_missing(
        ["ID_1", "ID_5", "ID_5", ""], cache, resolver=fake
    )
    assert calls == ["5"]
    assert cache["5"] == "Schweiz"
    assert (resolved, failed) == (1, 0)


def test_resolver_failure_is_counted_not_cached():
    def boom(object_id):
        raise RuntimeError("403")

    cache, resolved, failed = resolve_missing(["ID_7"], {}, resolver=boom)
    assert "7" not in cache  # a failed lookup must not look like "no Land"
    assert (resolved, failed) == (0, 1)


def test_cache_roundtrip(tmp_path):
    path = tmp_path / "cache.json"
    save_cache({"1": "Deutschland", "2": None}, str(path))
    assert load_cache(str(path)) == {"1": "Deutschland", "2": None}
    assert json.loads(path.read_text(encoding="utf-8"))["1"] == "Deutschland"


def test_load_cache_missing_file(tmp_path):
    assert load_cache(str(tmp_path / "absent.json")) == {}
