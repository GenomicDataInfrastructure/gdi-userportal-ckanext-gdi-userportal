# SPDX-FileCopyrightText: 2026 Stichting Health-RI
#
# SPDX-License-Identifier: Apache-2.0

"""
The conformance service behind the dataset-page indicator, the search badge, the report and the CLI.

Runs on the host with PyYAML and pytest, without CKAN:

    uv run --no-project --with pyyaml --with pytest python -I -m pytest \
        ckanext/gdi_userportal/tests/profile_packs/test_conformance_service.py
"""

import sys
from pathlib import Path

import pytest

# `python -I` ignores the working directory, so the extension is put on the path by hand.
sys.path.insert(0, str(Path(__file__).resolve().parents[4]))

from ckanext.gdi_userportal import conformance_service as service  # noqa: E402

from test_conformance import r8_dataset  # noqa: E402

BOTH = {"ckanext.dcat.metadata_profiles": "healthdcat_r8 gdi_current", "ckanext.dcat.metadata_profiles.main": "gdi_current"}


def dataset(name="one", **fields):
    return {"id": f"id-{name}", "name": name, "title": name.title(), "type": "dataset", **r8_dataset(), **fields}


class FakeSearch:
    """A package_search that serves ``datasets`` in pages and records the queries it got."""

    def __init__(self, datasets):
        self.datasets = datasets
        self.queries = []

    def __call__(self, query):
        self.queries.append(query)
        start, rows = query["start"], query["rows"]
        return {"count": len(self.datasets), "results": self.datasets[start : start + rows]}


# --- the page indicator ------------------------------------------------------------------


def test_a_conforming_dataset_conforms_to_every_enabled_profile():
    indicator = service.page_indicator(dataset(), BOTH)

    assert [entry["name"] for entry in indicator["profiles"]] == ["healthdcat_r8", "gdi_current"]
    assert all(entry["conformant"] for entry in indicator["profiles"])
    assert indicator["failing"] == []
    assert indicator["access_layer"] == "PUBLIC"


def test_a_missing_mandatory_property_is_named_and_listed_as_failing():
    indicator = service.page_indicator(dataset(theme=[]), BOTH)

    failing = indicator["failing"]
    assert [entry["name"] for entry in failing] == ["healthdcat_r8"]
    assert failing[0]["missing"] == ["theme"]
    assert failing[0]["conformant"] is False
    assert [entry["name"] for entry in indicator["profiles"] if entry["conformant"]] == ["gdi_current"]


def test_without_an_access_right_the_reason_is_given_instead_of_a_list():
    indicator = service.page_indicator(dataset(access_rights=None), BOTH)

    (failing,) = indicator["failing"]
    assert failing["missing"] == []
    assert "access rights is missing" in failing["reason"]
    assert indicator["access_layer"] is None


def test_only_the_enabled_profiles_are_shown():
    indicator = service.page_indicator(dataset(), {"ckanext.dcat.metadata_profiles": "gdi_current"})

    assert [entry["name"] for entry in indicator["profiles"]] == ["gdi_current"]


@pytest.mark.parametrize("record_type", ["dataset_series", "showcase"])
def test_a_record_that_is_not_a_dataset_gets_no_indicator(record_type):
    assert service.page_indicator(dataset(type=record_type), BOTH) is None


@pytest.mark.parametrize("record", [None, "a string", ["a", "list"], 5])
def test_a_page_never_fails_on_what_is_not_a_dataset(record):
    assert service.page_indicator(record, BOTH) is None


def test_a_dataset_of_the_old_shape_is_not_conformant_and_does_not_raise():
    old = {"id": "x", "name": "old", "title": "Old", "notes": None, "extras": [{"key": "guid", "value": "x"}]}

    indicator = service.page_indicator(old, BOTH)

    assert [entry["name"] for entry in indicator["failing"]] == ["healthdcat_r8"]


def test_a_broken_configuration_gives_no_indicator_instead_of_an_error():
    broken = {"ckanext.dcat.metadata_profiles": "no_such_profile"}

    assert service.page_indicator(dataset(), broken) is None


def test_a_dataset_without_a_type_is_a_dataset():
    record = dataset()
    del record["type"]

    assert service.page_indicator(record, BOTH)["failing"] == []


# --- the rules and the profiles ----------------------------------------------------------


def test_the_rules_of_a_profile_are_loaded_once():
    service.rules_for.cache_clear()

    assert service.rules_for("healthdcat_r8") is service.rules_for("healthdcat_r8")
    assert service.rules_for.cache_info().misses == 1


def test_a_profile_without_rules_has_none():
    assert service.rules_for("gdi_current") is None


def test_the_main_profile_defaults_to_the_first_enabled_one():
    enabled = service.enabled_profiles({"ckanext.dcat.metadata_profiles": "healthdcat_r8 gdi_current"})

    assert service.main_profile({}, enabled) == "healthdcat_r8"
    assert service.main_profile({"ckanext.dcat.metadata_profiles.main": " gdi_current "}, enabled) == "gdi_current"


# --- the report --------------------------------------------------------------------------


def test_the_report_lists_only_the_datasets_that_do_not_conform():
    search = FakeSearch([dataset("a"), dataset("b", theme=[]), dataset("c", access_rights=None)])

    report = service.conformance_report(search, BOTH)

    assert report["checked"] == 3
    assert report["enabled_profiles"] == ["healthdcat_r8", "gdi_current"]
    assert report["profiles"]["gdi_current"] == {"non_conformant": 0, "datasets": []}
    r8 = report["profiles"]["healthdcat_r8"]
    assert r8["non_conformant"] == 2
    assert [entry["name"] for entry in r8["datasets"]] == ["b", "c"]
    assert r8["datasets"][0] == {
        "id": "id-b",
        "name": "b",
        "title": "B",
        "access_layer": "PUBLIC",
        "missing": ["theme"],
    }
    assert r8["datasets"][1]["access_layer"] is None
    assert "access rights is missing" in r8["datasets"][1]["reason"]


def test_the_report_can_be_limited_to_one_profile():
    search = FakeSearch([dataset("a", theme=[])])

    report = service.conformance_report(search, BOTH, ["gdi_current"])

    assert list(report["profiles"]) == ["gdi_current"]
    assert report["profiles"]["gdi_current"]["non_conformant"] == 0
    assert report["enabled_profiles"] == ["healthdcat_r8", "gdi_current"]


def test_the_report_reads_every_page_of_the_search(monkeypatch):
    monkeypatch.setattr(service, "REPORT_PAGE_SIZE", 2)
    search = FakeSearch([dataset(f"d{index}", theme=[]) for index in range(5)])

    report = service.conformance_report(search, BOTH)

    assert report["checked"] == 5
    assert report["profiles"]["healthdcat_r8"]["non_conformant"] == 5
    assert [query["start"] for query in search.queries] == [0, 2, 4]


def test_the_report_asks_for_datasets_only_and_includes_private_ones():
    search = FakeSearch([])

    report = service.conformance_report(search, BOTH)

    assert report["checked"] == 0
    (query,) = search.queries
    assert query["fq"] == "+dataset_type:dataset"
    assert query["include_private"] is True
    assert query["sort"] == "name asc"


def test_the_report_stops_when_the_search_returns_nothing_more():
    calls = []

    def lying_search(query):
        calls.append(query["start"])
        return {"count": 100, "results": [dataset("only")] if len(calls) == 1 else []}

    report = service.conformance_report(lying_search, BOTH)

    assert report["checked"] == 1
    assert calls == [0, 1]


def test_the_report_names_the_title_or_else_the_name():
    untitled = dataset("untitled", theme=[])
    del untitled["title"]

    report = service.conformance_report(FakeSearch([untitled]), BOTH)

    assert report["profiles"]["healthdcat_r8"]["datasets"][0]["title"] == "untitled"


# --- what the command prints -------------------------------------------------------------


def test_the_report_is_printed_per_profile():
    search = FakeSearch([dataset("a"), dataset("b", theme=[]), dataset("c", access_rights=None)])
    report = service.conformance_report(search, BOTH)

    lines = service.format_report(report)

    assert lines[0] == "Checked 3 dataset(s) against: healthdcat_r8, gdi_current"
    assert "healthdcat_r8: 2 of 3 do not conform" in lines
    assert "  b [PUBLIC]: missing theme" in lines
    assert any(line.startswith("  c: access rights is missing") for line in lines)
    assert "gdi_current: all conform" in lines


def test_an_empty_catalogue_conforms_everywhere():
    lines = service.format_report(service.conformance_report(FakeSearch([]), BOTH))

    assert lines == [
        "Checked 0 dataset(s) against: healthdcat_r8, gdi_current",
        "healthdcat_r8: all conform",
        "gdi_current: all conform",
    ]
