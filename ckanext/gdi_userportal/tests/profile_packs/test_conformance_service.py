# SPDX-FileCopyrightText: 2026 Stichting Health-RI
#
# SPDX-License-Identifier: Apache-2.0

"""
The conformance service behind the dataset, series, distribution and search indicators, the report and the CLI.

Runs on the host with PyYAML and pytest, without CKAN:

    uv run --no-project --with pyyaml --with pytest python -I -m pytest \
        ckanext/gdi_userportal/tests/profile_packs/test_conformance_service.py
"""

import json
import sys
from pathlib import Path

import pytest

# `python -I` ignores the working directory, so the extension is put on the path by hand.
sys.path.insert(0, str(Path(__file__).resolve().parents[4]))

from ckanext.gdi_userportal import conformance_service as service  # noqa: E402

from test_conformance import r8_dataset  # noqa: E402

BOTH = {"ckanext.dcat.metadata_profiles": "healthdcat_r8 gdi_current", "ckanext.dcat.metadata_profiles.main": "gdi_current"}
LAW = ["http://data.europa.eu/eli/reg/2025/327/oj"]
R8_SOURCE, GDI_SOURCE, PLAIN_SOURCE = "src-r8", "src-gdi", "src-plain"
SOURCES = {R8_SOURCE: "healthdcat_r8", GDI_SOURCE: "gdi_current", PLAIN_SOURCE: None}


def resource(rid="r1", uri=None, law=True, **fields):
    record = {"id": rid, "name_translated": {"en": f"Resource {rid}"}, "url": f"https://example.org/{rid}", **fields}
    if uri:
        record["uri"] = uri
    if law:
        record["applicable_legislation"] = LAW
    return record


def dataset(name="one", source=None, **fields):
    record = {"id": f"id-{name}", "name": name, "title": name.title(), "type": "dataset", **r8_dataset(), **fields}
    record["resources"] = fields.get("resources", [resource()])
    if source:
        record["extras"] = [{"key": "harvest_source_id", "value": source}]
    return record


def series(name="ser", source=None, **fields):
    record = {"id": f"id-{name}", "name": name, "title": name.title(), "type": "dataset_series", "applicable_legislation": LAW}
    record.update(fields)
    if source:
        record["extras"] = [{"key": "harvest_source_id", "value": source}]
    return record


class Lookup:
    """The source lookup: answers from SOURCES and records the ids it was asked for."""

    def __init__(self, known=None):
        self.known = SOURCES if known is None else known
        self.calls = []

    def __call__(self, source_ids):
        ids = sorted(source_ids)
        self.calls.append(ids)
        return {source_id: self.known[source_id] for source_id in ids if source_id in self.known}


class FakeSearch:
    """A package_search that serves records by ``dataset_type`` in pages and records the queries it got."""

    def __init__(self, datasets=(), series_records=()):
        self.records = {"dataset": list(datasets), "dataset_series": list(series_records)}
        self.queries = []

    def __call__(self, query):
        self.queries.append(query)
        records = self.records[query["fq"].split(":")[1]]
        start, rows = query["start"], query["rows"]
        return {"count": len(records), "results": records[start : start + rows]}


# --- which profiles a record is checked against ----------------------------------------------


def test_the_source_of_a_record_is_read_from_its_extras_or_its_own_key():
    assert service.source_id_of({"extras": [{"key": "guid", "value": "g"}, {"key": "harvest_source_id", "value": " s1 "}]}) == "s1"
    assert service.source_id_of({"extras": {"harvest_source_id": "s2"}}) == "s2"
    assert service.source_id_of({"harvest_source_id": "s3"}) == "s3"


@pytest.mark.parametrize("record", [{}, {"extras": []}, {"extras": None}, {"extras": [{"key": "harvest_source_id", "value": " "}]}, {"extras": ["x"]}])
def test_a_record_without_a_source_has_none(record):
    assert service.source_id_of(record) is None


def test_a_record_of_a_source_is_checked_against_the_profile_the_source_names():
    applicable = service.applicable_profiles(dataset(source=R8_SOURCE), ["healthdcat_r8", "gdi_current"], "gdi_current", SOURCES)

    assert applicable == (["healthdcat_r8"], "source", "healthdcat_r8")


def test_a_source_that_names_no_profile_means_the_main_profile():
    applicable = service.applicable_profiles(dataset(source=PLAIN_SOURCE), ["healthdcat_r8", "gdi_current"], "gdi_current", SOURCES)

    assert applicable == (["gdi_current"], "main", None)


@pytest.mark.parametrize("record", [dataset(), dataset(source="vanished-source")])
def test_a_record_no_source_says_anything_about_is_checked_against_every_enabled_profile(record):
    applicable = service.applicable_profiles(record, ["healthdcat_r8", "gdi_current"], "gdi_current", SOURCES)

    assert applicable == (["healthdcat_r8", "gdi_current"], "enabled", None)


def test_a_source_whose_profile_is_not_enabled_leaves_nothing_to_check():
    applicable = service.applicable_profiles(dataset(source=R8_SOURCE), ["gdi_current"], "gdi_current", SOURCES)

    assert applicable == ([], "source", "healthdcat_r8")


# --- the page indicator of a dataset ---------------------------------------------------------


def test_a_dataset_without_a_source_conforms_to_every_enabled_profile():
    indicator = service.page_indicator(dataset(), BOTH)

    assert indicator["kind"] == "dataset"
    assert indicator["basis"] == "enabled"
    assert [entry["name"] for entry in indicator["profiles"]] == ["healthdcat_r8", "gdi_current"]
    assert all(entry["conformant"] for entry in indicator["profiles"])
    assert indicator["failing"] == []
    assert indicator["access_layer"] == "PUBLIC"


def test_a_missing_mandatory_property_is_named_and_listed_as_failing():
    indicator = service.page_indicator(dataset(theme=[]), BOTH)

    failing = indicator["failing"]
    assert [entry["name"] for entry in failing] == ["healthdcat_r8"]
    assert failing[0]["missing"] == ["theme"]
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


def test_a_dataset_of_a_gdi_current_source_is_not_checked_against_r8():
    lookup = Lookup()

    indicator = service.page_indicator(dataset(source=GDI_SOURCE, theme=[]), BOTH, lookup)

    assert indicator["basis"] == "source"
    assert [entry["name"] for entry in indicator["profiles"]] == ["gdi_current"]
    assert indicator["failing"] == []
    assert lookup.calls == [[GDI_SOURCE]]


def test_a_dataset_of_an_r8_source_is_checked_against_r8_only():
    indicator = service.page_indicator(dataset(source=R8_SOURCE, theme=[]), BOTH, Lookup())

    assert [entry["name"] for entry in indicator["profiles"]] == ["healthdcat_r8"]
    assert [entry["name"] for entry in indicator["failing"]] == ["healthdcat_r8"]


def test_a_dataset_of_a_source_without_a_profile_is_checked_against_the_main_profile():
    indicator = service.page_indicator(dataset(source=PLAIN_SOURCE, theme=[]), BOTH, Lookup())

    assert indicator["basis"] == "main"
    assert [entry["name"] for entry in indicator["profiles"]] == ["gdi_current"]


def test_a_dataset_of_an_unknown_source_is_checked_against_every_enabled_profile():
    indicator = service.page_indicator(dataset(source="vanished-source"), BOTH, Lookup())

    assert indicator["basis"] == "enabled"
    assert len(indicator["profiles"]) == 2


def test_a_dataset_of_a_source_whose_profile_is_not_enabled_gets_no_indicator():
    assert service.page_indicator(dataset(source=R8_SOURCE), {"ckanext.dcat.metadata_profiles": "gdi_current"}, Lookup()) is None


def test_the_source_is_not_looked_up_for_a_dataset_without_one():
    lookup = Lookup()

    service.page_indicator(dataset(), BOTH, lookup)

    assert lookup.calls == []


def test_a_record_that_is_neither_a_dataset_nor_a_series_gets_no_indicator():
    assert service.page_indicator(dataset(type="showcase"), BOTH) is None


@pytest.mark.parametrize("record", [None, "a string", ["a", "list"], 5])
def test_a_page_never_fails_on_what_is_not_a_record(record):
    assert service.page_indicator(record, BOTH) is None


def test_a_dataset_of_the_old_shape_is_not_conformant_and_does_not_raise():
    old = {"id": "x", "name": "old", "title": "Old", "notes": None, "extras": [{"key": "guid", "value": "x"}], "resources": ["junk", None]}

    indicator = service.page_indicator(old, BOTH)

    assert [entry["name"] for entry in indicator["failing"]] == ["healthdcat_r8"]
    assert indicator["distributions"] == []


def test_a_broken_configuration_gives_no_indicator_instead_of_an_error():
    assert service.page_indicator(dataset(), {"ckanext.dcat.metadata_profiles": "no_such_profile"}) is None


def test_a_failing_lookup_gives_no_indicator_instead_of_an_error():
    def broken(source_ids):
        raise RuntimeError("database down")

    assert service.page_indicator(dataset(source=R8_SOURCE), BOTH, broken) is None


def test_a_dataset_without_a_type_is_a_dataset():
    record = dataset()
    del record["type"]

    assert service.page_indicator(record, BOTH)["kind"] == "dataset"


# --- dataset series --------------------------------------------------------------------------


def test_a_series_with_applicable_legislation_conforms_and_has_no_access_layer():
    indicator = service.page_indicator(series(), BOTH)

    assert indicator["kind"] == "dataset_series"
    assert indicator["access_layer"] is None
    assert indicator["failing"] == []
    assert indicator["distributions"] == []


def test_a_series_without_applicable_legislation_fails_r8_and_names_it():
    indicator = service.page_indicator(series(applicable_legislation=[]), BOTH)

    (failing,) = indicator["failing"]
    assert (failing["name"], failing["missing"]) == ("healthdcat_r8", ["applicable legislation"])


def test_a_series_of_a_source_is_checked_against_the_profile_of_that_source():
    indicator = service.page_indicator(series(source=GDI_SOURCE, applicable_legislation=None), BOTH, Lookup())

    assert [entry["name"] for entry in indicator["profiles"]] == ["gdi_current"]
    assert indicator["failing"] == []


def test_a_series_of_the_old_shape_does_not_raise():
    indicator = service.page_indicator({"id": "s", "name": "s", "type": "dataset_series", "extras": "junk"}, BOTH)

    assert [entry["name"] for entry in indicator["failing"]] == ["healthdcat_r8"]


# --- distributions: plain, sample and analytics -----------------------------------------------


def test_a_sample_and_an_analytics_distribution_are_distributions_with_their_own_label():
    record = dataset(
        sample=["https://example.org/sample"],
        analytics=["https://example.org/analytics"],
        resources=[
            resource("main", uri="https://example.org/main"),
            resource("smp", uri="https://example.org/sample"),
            resource("ana", uri="https://example.org/analytics"),
        ],
    )

    distributions = service.page_indicator(record, BOTH)["distributions"]

    assert [(item["id"], item["kind"]) for item in distributions] == [("main", "distribution"), ("smp", "sample"), ("ana", "analytics")]
    assert all(not item["failing"] for item in distributions)


def test_a_sample_without_applicable_legislation_fails_like_any_other_distribution():
    record = dataset(sample=["https://example.org/sample"], resources=[resource("smp", uri="https://example.org/sample", law=False)])

    (item,) = service.page_indicator(record, BOTH)["distributions"]

    assert item["kind"] == "sample"
    assert [(entry["name"], entry["missing"]) for entry in item["failing"]] == [("healthdcat_r8", ["applicable legislation"])]


def test_the_distributions_are_checked_against_the_profile_of_the_dataset_source():
    record = dataset(source=GDI_SOURCE, resources=[resource(law=False)])

    (item,) = service.page_indicator(record, BOTH, Lookup())["distributions"]

    assert [entry["name"] for entry in item["profiles"]] == ["gdi_current"]
    assert item["failing"] == []


def test_a_sample_counts_as_a_distribution_of_the_dataset():
    only_a_sample = dataset(sample=["https://example.org/sample"], resources=[resource("smp", uri="https://example.org/sample")])

    result = service.evaluate_dataset(only_a_sample, BOTH, ["healthdcat_r8"])

    assert result["profiles"]["healthdcat_r8"]["conformant"] is True


def test_the_kind_comes_from_the_uri_in_the_sample_or_analytics_list():
    record = {"sample": '["https://example.org/a", "https://example.org/b"]', "analytics": ["https://example.org/c"]}

    assert service.resource_kind(record, {"uri": "https://example.org/b"}) == "sample"
    assert service.resource_kind(record, {"uri": " https://example.org/c "}) == "analytics"
    assert service.resource_kind(record, {"uri": "https://example.org/other"}) == "distribution"


@pytest.mark.parametrize("resource_record", [{}, {"uri": ""}, {"uri": None}, {"uri": 5}, "junk", None])
def test_a_distribution_without_a_usable_uri_is_a_plain_distribution(resource_record):
    assert service.resource_kind({"sample": ["x"], "analytics": ["x"]}, resource_record) == "distribution"


@pytest.mark.parametrize("sample", [None, "", "[not json", 5, {"a": 1}])
def test_a_sample_list_of_any_shape_does_not_raise(sample):
    assert service.resource_kind({"sample": sample}, {"uri": "x"}) == "distribution"


@pytest.mark.parametrize(
    "record, name",
    [
        ({"name_translated": {"en": "English", "nl": "Nederlands"}, "name": "n"}, "English"),
        ({"name_translated": {"en": "", "nl": "Nederlands"}, "name": "n"}, "Nederlands"),
        ({"name_translated": {}, "name": "Plain"}, "Plain"),
        ({"url": "https://example.org/u"}, "https://example.org/u"),
        ({"id": "r9"}, "r9"),
        ({}, ""),
    ],
)
def test_a_distribution_is_named_by_its_title_name_url_or_id(record, name):
    assert service.resource_name(record) == name


def test_one_distribution_can_be_judged_on_its_own():
    record = dataset(sample=["https://example.org/sample"])
    smp = resource("smp", uri="https://example.org/sample", law=False)

    indicator = service.resource_indicator(record, smp, BOTH)

    assert indicator["kind"] == "sample"
    assert indicator["basis"] == "enabled"
    assert [entry["name"] for entry in indicator["failing"]] == ["healthdcat_r8"]


def test_one_distribution_follows_the_profile_of_its_dataset_source():
    indicator = service.resource_indicator(dataset(source=GDI_SOURCE), resource(law=False), BOTH, Lookup())

    assert [entry["name"] for entry in indicator["profiles"]] == ["gdi_current"]
    assert indicator["failing"] == []


@pytest.mark.parametrize("record, res", [(None, {}), ({"type": "dataset_series"}, {}), (dataset(), None), (dataset(), "junk")])
def test_a_distribution_page_never_fails_on_what_is_not_a_dataset_and_a_distribution(record, res):
    assert service.resource_indicator(record, res, BOTH) is None


def test_the_distributions_of_a_dataset_are_evaluated_for_every_enabled_profile():
    record = dataset(resources=[resource("ok"), resource("bad", law=False), "junk"])

    items = service.evaluate_distributions(record, BOTH)

    assert [(item["id"], item["conformant_profiles"]) for item in items] == [
        ("ok", ["healthdcat_r8", "gdi_current"]),
        ("bad", ["gdi_current"]),
    ]


# --- the rules ---------------------------------------------------------------------------------


def test_the_rules_of_a_profile_are_loaded_once():
    service.rules_for.cache_clear()

    assert service.rules_for("healthdcat_r8") is service.rules_for("healthdcat_r8")
    assert service.rules_for.cache_info().misses == 1


def test_a_profile_without_rules_has_none():
    assert service.rules_for("gdi_current") is None


def test_r8_makes_applicable_legislation_mandatory_for_distributions_and_series():
    classes = service.rules_for("healthdcat_r8")["classes"]

    assert [rule["property"] for rule in classes["distribution"]["mandatory"]] == ["applicable legislation"]
    assert [rule["property"] for rule in classes["series"]["mandatory"]] == ["applicable legislation"]


def test_the_main_profile_defaults_to_the_first_enabled_one():
    enabled = service.enabled_profiles({"ckanext.dcat.metadata_profiles": "healthdcat_r8 gdi_current"})

    assert service.main_profile({}, enabled) == "healthdcat_r8"
    assert service.main_profile({"ckanext.dcat.metadata_profiles.main": " gdi_current "}, enabled) == "gdi_current"


# --- the report --------------------------------------------------------------------------------


def report(search, profiles=None, lookup=None):
    return service.conformance_report(search, BOTH, profiles, lookup)


def test_the_report_lists_only_what_does_not_conform_per_class():
    search = FakeSearch(
        [dataset("a"), dataset("b", theme=[]), dataset("c", access_rights=None, resources=[resource("c1", law=False)])],
        [series("s-ok"), series("s-bad", applicable_legislation=[])],
    )

    result = report(search)

    assert (result["checked"], result["checked_series"], result["checked_distributions"]) == (3, 2, 3)
    r8 = result["profiles"]["healthdcat_r8"]
    assert [item["name"] for item in r8["datasets"]["items"]] == ["b", "c"]
    assert (r8["datasets"]["checked"], r8["datasets"]["non_conformant"]) == (3, 2)
    assert [item["name"] for item in r8["series"]["items"]] == ["s-bad"]
    assert [(item["dataset"], item["name"]) for item in r8["distributions"]["items"]] == [("c", "Resource c1")]
    gdi = result["profiles"]["gdi_current"]
    assert all(gdi[key]["non_conformant"] == 0 for key in ("datasets", "series", "distributions"))


def test_the_items_say_what_is_missing_and_where():
    search = FakeSearch(
        [dataset("b", theme=[], sample=["https://example.org/s"], resources=[resource("b1", uri="https://example.org/s", law=False)])],
        [series("s-bad", applicable_legislation=[])],
    )

    r8 = report(search)["profiles"]["healthdcat_r8"]

    assert r8["datasets"]["items"][0] == {
        "id": "id-b", "name": "b", "title": "B", "access_layer": "PUBLIC", "missing": ["theme"],
    }
    assert r8["series"]["items"][0] == {
        "id": "id-s-bad", "name": "s-bad", "title": "S-Bad", "access_layer": None, "missing": ["applicable legislation"],
    }
    assert r8["distributions"]["items"][0] == {
        "id": "b1", "name": "Resource b1", "kind": "sample", "dataset": "b", "dataset_id": "id-b", "missing": ["applicable legislation"],
    }


def test_a_record_without_an_access_right_is_listed_with_the_reason():
    r8 = report(FakeSearch([dataset("c", access_rights=None)]))["profiles"]["healthdcat_r8"]

    (item,) = r8["datasets"]["items"]
    assert item["access_layer"] is None and item["missing"] == []
    assert "access rights is missing" in item["reason"]


def test_each_record_is_checked_against_the_profile_it_comes_from_only():
    search = FakeSearch(
        [
            dataset("gdi", source=GDI_SOURCE, theme=[], resources=[resource(law=False)]),
            dataset("r8", source=R8_SOURCE, theme=[]),
            dataset("plain", source=PLAIN_SOURCE, theme=[]),
            dataset("hand", theme=[]),
        ],
        [series("s-gdi", source=GDI_SOURCE, applicable_legislation=[]), series("s-r8", source=R8_SOURCE, applicable_legislation=[])],
    )

    profiles = report(search, lookup=Lookup())["profiles"]

    r8 = profiles["healthdcat_r8"]
    assert [item["name"] for item in r8["datasets"]["items"]] == ["r8", "hand"]
    assert r8["datasets"]["checked"] == 2  # the gdi and plain datasets are not R8's to judge
    assert [item["name"] for item in r8["series"]["items"]] == ["s-r8"]
    assert r8["series"]["checked"] == 1
    gdi = profiles["gdi_current"]
    assert gdi["datasets"]["checked"] == 3  # gdi, plain and the one made by hand
    assert gdi["datasets"]["non_conformant"] == 0
    assert gdi["distributions"]["non_conformant"] == 0


def test_the_sources_of_a_page_are_looked_up_in_one_call():
    lookup = Lookup()

    report(FakeSearch([dataset("a", source=GDI_SOURCE), dataset("b", source=R8_SOURCE), dataset("c")]), lookup=lookup)

    assert lookup.calls == [sorted([GDI_SOURCE, R8_SOURCE])]


def test_the_report_can_be_limited_to_one_profile():
    search = FakeSearch([dataset("a", theme=[])])

    result = report(search, ["gdi_current"])

    assert list(result["profiles"]) == ["gdi_current"]
    assert result["profiles"]["gdi_current"]["datasets"]["non_conformant"] == 0
    assert result["enabled_profiles"] == ["healthdcat_r8", "gdi_current"]


def test_the_report_reads_every_page_of_datasets_and_of_series(monkeypatch):
    monkeypatch.setattr(service, "REPORT_PAGE_SIZE", 2)
    search = FakeSearch([dataset(f"d{index}", theme=[]) for index in range(5)], [series(f"s{index}") for index in range(3)])

    result = report(search)

    assert (result["checked"], result["checked_series"]) == (5, 3)
    assert result["profiles"]["healthdcat_r8"]["datasets"]["non_conformant"] == 5
    assert [(query["fq"], query["start"]) for query in search.queries] == [
        ("+dataset_type:dataset", 0), ("+dataset_type:dataset", 2), ("+dataset_type:dataset", 4),
        ("+dataset_type:dataset_series", 0), ("+dataset_type:dataset_series", 2),
    ]


def test_the_report_includes_private_records_and_sorts_by_name():
    search = FakeSearch([dataset("a")])

    report(search)

    assert all(query["include_private"] is True and query["sort"] == "name asc" for query in search.queries)


def test_the_report_of_an_empty_catalogue_has_nothing_to_list():
    result = report(FakeSearch())

    assert (result["checked"], result["checked_series"], result["checked_distributions"]) == (0, 0, 0)
    assert all(section["items"] == [] for section in result["profiles"]["healthdcat_r8"].values())


def test_the_report_stops_when_the_search_returns_nothing_more():
    calls = []

    def lying_search(query):
        calls.append((query["fq"], query["start"]))
        first = query["fq"].endswith(":dataset") and len(calls) == 1
        return {"count": 100, "results": [dataset("only")] if first else []}

    result = report(lying_search)

    assert result["checked"] == 1
    assert calls == [("+dataset_type:dataset", 0), ("+dataset_type:dataset", 1), ("+dataset_type:dataset_series", 0)]


def test_a_record_of_the_old_shape_does_not_break_the_report():
    result = report(FakeSearch([{"id": "x", "name": "old", "type": "dataset", "resources": ["junk"], "extras": 5}]))

    assert result["profiles"]["healthdcat_r8"]["datasets"]["non_conformant"] == 1


def test_the_report_names_the_title_or_else_the_name():
    untitled = dataset("untitled", theme=[])
    del untitled["title"]

    r8 = report(FakeSearch([untitled]))["profiles"]["healthdcat_r8"]

    assert r8["datasets"]["items"][0]["title"] == "untitled"


# --- what the command prints -------------------------------------------------------------------


def test_the_report_is_printed_per_profile_and_class():
    search = FakeSearch(
        [dataset("a"), dataset("b", theme=[], resources=[resource("b1", law=False)]), dataset("c", access_rights=None)],
        [series("s-bad", applicable_legislation=[])],
    )

    lines = service.format_report(report(search))

    assert lines[0] == "Checked 3 dataset(s), 1 series and 3 distribution(s)"
    assert "healthdcat_r8: 2 of 3 dataset(s) do not conform; 1 of 1 series do not conform; 1 of 3 distribution(s) do not conform" in lines
    assert "  b [PUBLIC]: missing theme" in lines
    assert any(line.startswith("  c: access rights is missing") for line in lines)
    assert "  series s-bad: missing applicable legislation" in lines
    assert "  b / Resource b1 (distribution): missing applicable legislation" in lines
    assert "gdi_current: all conform (3 dataset(s), 1 series, 3 distribution(s))" in lines


def test_an_empty_catalogue_conforms_everywhere():
    lines = service.format_report(report(FakeSearch()))

    assert lines == [
        "Checked 0 dataset(s), 0 series and 0 distribution(s)",
        "healthdcat_r8: all conform (0 dataset(s), 0 series, 0 distribution(s))",
        "gdi_current: all conform (0 dataset(s), 0 series, 0 distribution(s))",
    ]


def test_the_report_is_plain_json():
    json.dumps(report(FakeSearch([dataset("a", theme=[])], [series("s")])))
