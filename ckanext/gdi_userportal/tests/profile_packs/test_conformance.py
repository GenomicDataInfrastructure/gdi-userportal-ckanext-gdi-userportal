# SPDX-FileCopyrightText: 2026 Stichting Health-RI
#
# SPDX-License-Identifier: Apache-2.0

"""
Computed conformance: which enabled profiles a dataset satisfies at its access layer.

The central promise is that data never raises: whatever is missing or malformed gives
"not conformant", with the missing properties named.
"""

import copy

import pytest

PUBLIC = "http://publications.europa.eu/resource/authority/access-right/PUBLIC"
RESTRICTED = "http://publications.europa.eu/resource/authority/access-right/RESTRICTED"
NON_PUBLIC = "http://publications.europa.eu/resource/authority/access-right/NON_PUBLIC"

# CKAN core fields that mandatory properties map onto next to the scheming fields.
CORE_FIELDS = {"title", "notes", "tags", "resources"}


def r8_dataset(access_rights=PUBLIC):
    """A dataset that has every property R8 makes mandatory in the public and restricted layers."""
    return {
        "access_rights": access_rights,
        "applicable_legislation": ["http://data.europa.eu/eli/reg/2025/327/oj"],
        "resources": [{"id": "r1", "url": "https://example.org/file.csv"}],
        "notes_translated": {"en": "A description", "nl": ""},
        "health_category": ["https://example.org/category"],
        "hdab": [{"name": "Access body", "email": "hdab@example.org"}],
        "identifier": "ds-1",
        "has_structured_data": False,
        "theme": ["http://publications.europa.eu/resource/authority/data-theme/HEAL"],
        "title_translated": {"en": "A title"},
    }


def non_public_dataset():
    dataset = r8_dataset(NON_PUBLIC)
    dataset.update(
        {
            "contact": [{"name": "Support", "email": "support@example.org"}],
            "tags_translated": {"en": ["cancer"]},
            "provenance": "Collected from hospitals",
            "dcat_type": "http://publications.europa.eu/resource/authority/dataset-type/PERSONAL_DATA",
        }
    )
    return dataset


def evaluate(conformance, r8_rules, dataset, profiles=("healthdcat_r8",), rules=None):
    return conformance.evaluate(dataset, list(profiles), rules or {"healthdcat_r8": r8_rules})


def r8_result(conformance, r8_rules, dataset):
    return evaluate(conformance, r8_rules, dataset)["profiles"]["healthdcat_r8"]


def missing(result):
    return {item["property"] for item in result["missing"]}


# --- what counts as a value ----------------------------------------------------------


@pytest.mark.parametrize(
    "value",
    [None, "", "   ", [], {}, [None], [""], [{}], [{"name": "", "email": " "}], {"en": "", "nl": None}, "[]", "{}", "[{}]", '{"en": ""}'],
)
def test_nothing_is_not_a_value(conformance, value):
    assert conformance.is_filled(value) is False


@pytest.mark.parametrize(
    "value",
    ["x", False, True, 0, 0.0, 12, ["a"], [{"name": "a"}], {"en": "a"}, {"en": "", "nl": "b"}, '["a"]', '{"en": "a"}', "[not json", "{"],
)
def test_something_is_a_value(conformance, value):
    assert conformance.is_filled(value) is True


def test_a_value_nested_beyond_the_json_decoder_is_still_an_answer(conformance):
    assert conformance.is_filled("[" * 100_000 + "]" * 100_000) is True


# --- the access layer ----------------------------------------------------------------


@pytest.mark.parametrize(
    "value, layer",
    [
        (PUBLIC, "PUBLIC"),
        (RESTRICTED, "RESTRICTED"),
        (NON_PUBLIC, "NON_PUBLIC"),
        ("NON_PUBLIC", "NON_PUBLIC"),
        ("non-public", "NON_PUBLIC"),
        ("Non Public", "NON_PUBLIC"),
        (NON_PUBLIC + "/", "NON_PUBLIC"),
        ("http://example.org/ns#RESTRICTED", "RESTRICTED"),
        ([NON_PUBLIC], "NON_PUBLIC"),
        (["", PUBLIC], "PUBLIC"),
        ({"en": PUBLIC}, "PUBLIC"),
        ('["' + RESTRICTED + '"]', "RESTRICTED"),  # extras can hold JSON text
        ('{"en": "' + NON_PUBLIC + '"}', "NON_PUBLIC"),
    ],
)
def test_the_layer_comes_from_the_last_segment_of_access_rights(conformance, value, layer):
    assert conformance.access_layer({"access_rights": value}) == (layer, None)


@pytest.mark.parametrize("value", [None, "", "  ", [], {}, 5, True, "[]", "{}", '[""]'])
def test_a_missing_access_right_gives_no_layer(conformance, value):
    layer, problem = conformance.access_layer({"access_rights": value})
    assert layer is None and "missing" in problem


def test_an_access_right_that_is_no_layer_is_named(conformance):
    layer, problem = conformance.access_layer(
        {"access_rights": "http://publications.europa.eu/resource/authority/access-right/CONFIDENTIAL"}
    )
    assert layer is None
    assert "CONFIDENTIAL" in problem and "NON_PUBLIC" in problem


@pytest.mark.parametrize("value", ["[draft] PUBLIC", "[", '{"en": ', "[1, 2]"])
def test_text_that_only_looks_like_json_is_no_layer_and_does_not_raise(conformance, value):
    assert conformance.access_layer({"access_rights": value})[0] is None


def test_a_dataset_without_access_rights_at_all_gives_no_layer(conformance):
    assert conformance.access_layer({})[0] is None


# --- the shipped R8 rules ------------------------------------------------------------


@pytest.mark.parametrize("access_rights", [PUBLIC, RESTRICTED])
def test_a_complete_public_or_restricted_dataset_conforms(conformance, r8_rules, access_rights):
    result = evaluate(conformance, r8_rules, r8_dataset(access_rights))
    assert result["conformant_profiles"] == ["healthdcat_r8"]
    assert result["profiles"]["healthdcat_r8"] == {"conformant": True, "mandatory": 10, "missing": []}


def test_a_complete_non_public_dataset_conforms_with_its_four_extra_properties(conformance, r8_rules):
    result = r8_result(conformance, r8_rules, non_public_dataset())
    assert result == {"conformant": True, "mandatory": 14, "missing": []}


def test_the_non_public_layer_asks_for_what_the_others_do_not(conformance, r8_rules):
    dataset = r8_dataset(NON_PUBLIC)  # complete for public, but not for non-public
    result = r8_result(conformance, r8_rules, dataset)
    assert result["conformant"] is False
    assert missing(result) == {"contact point", "keyword", "provenance", "type"}
    assert r8_result(conformance, r8_rules, {**dataset, "access_rights": PUBLIC})["conformant"] is True


@pytest.mark.parametrize(
    "field, property_label",
    [
        ("access_rights", "access rights"),
        ("applicable_legislation", "applicable legislation"),
        ("resources", "dataset distribution"),
        ("health_category", "health category"),
        ("hdab", "health data access body"),
        ("identifier", "identifier"),
        ("has_structured_data", "structured data"),
        ("theme", "theme"),
    ],
)
def test_each_missing_mandatory_property_is_named(conformance, r8_rules, field, property_label):
    dataset = r8_dataset()
    del dataset[field]
    result = r8_result(conformance, r8_rules, dataset)
    if field == "access_rights":  # without it there is no layer to be conformant at
        assert result["conformant"] is False and "access rights" in result["reason"]
    else:
        assert missing(result) == {property_label}


def test_the_title_and_the_description_may_come_from_the_core_fields(conformance, r8_rules):
    dataset = r8_dataset()
    del dataset["title_translated"], dataset["notes_translated"]
    assert missing(r8_result(conformance, r8_rules, dataset)) == {"title", "description"}
    dataset.update({"title": "An old title", "notes": "An old description"})
    assert r8_result(conformance, r8_rules, dataset)["conformant"] is True


def test_a_property_names_the_fields_that_would_fill_it(conformance, r8_rules):
    dataset = r8_dataset()
    del dataset["notes_translated"]
    assert r8_result(conformance, r8_rules, dataset)["missing"] == [
        {"property": "description", "fields": ["notes_translated", "notes"]}
    ]


def test_false_structured_data_is_an_answer_not_a_gap(conformance, r8_rules):
    dataset = r8_dataset()
    dataset["has_structured_data"] = False
    assert r8_result(conformance, r8_rules, dataset)["conformant"] is True


def test_a_blank_repeating_row_does_not_fill_a_property(conformance, r8_rules):
    dataset = r8_dataset()
    dataset["hdab"] = [{"name": "", "email": "", "url": None}]
    assert missing(r8_result(conformance, r8_rules, dataset)) == {"health data access body"}


# --- missing or malformed data never raises -----------------------------------------------------------


def test_an_empty_dataset_is_not_conformant_and_does_not_raise(conformance, r8_rules):
    result = evaluate(conformance, r8_rules, {})
    assert result["access_layer"] is None
    assert result["conformant_profiles"] == []
    assert "access rights is missing" in result["profiles"]["healthdcat_r8"]["reason"]


def test_a_dataset_with_only_core_fields_is_not_conformant(conformance, r8_rules):
    old = {"id": "x", "name": "old", "title": "Old", "notes": "Old", "tags": [{"name": "a"}], "resources": []}
    assert evaluate(conformance, r8_rules, old)["conformant_profiles"] == []


def test_without_a_layer_the_reason_says_so_instead_of_listing_properties(conformance, r8_rules):
    result = r8_result(conformance, r8_rules, {"title": "Old", "access_rights": ""})
    assert result["conformant"] is False
    assert result["missing"] == []
    assert result["reason"] == "access rights is missing"


GARBAGE = [None, "", 0, 1, -1, 1.5, True, False, [], {}, "x", ["x"], [None], [[]], [[[["x"]]]], {"a": {"b": {"c": []}}}, object(), b"bytes", "[", "{[}", "null", "[null]"]


@pytest.mark.parametrize("garbage", GARBAGE, ids=repr)
def test_no_value_shape_in_any_field_can_raise(conformance, r8_rules, garbage):
    fields = {field for layer in r8_rules["layers"].values() for rule in layer["mandatory"] for field in rule["fields"]}
    for access_rights in (PUBLIC, RESTRICTED, NON_PUBLIC, garbage):
        dataset = {field: copy.copy(garbage) for field in fields}
        dataset["access_rights"] = access_rights
        result = evaluate(conformance, r8_rules, dataset)
        assert isinstance(result["profiles"]["healthdcat_r8"]["conformant"], bool)


# --- several profiles ----------------------------------------------------------------


def test_a_profile_without_mandatory_properties_is_satisfied_by_any_dataset(conformance, r8_rules):
    result = conformance.evaluate({}, ["gdi_current"], {"gdi_current": None})
    assert result["profiles"]["gdi_current"] == {"conformant": True, "mandatory": 0, "missing": []}
    assert result["conformant_profiles"] == ["gdi_current"]


def test_each_enabled_profile_gets_its_own_answer(conformance, r8_rules):
    rules = {"gdi_current": None, "healthdcat_r8": r8_rules}
    dataset = r8_dataset()
    del dataset["hdab"]
    result = conformance.evaluate(dataset, ["gdi_current", "healthdcat_r8"], rules)
    assert result["conformant_profiles"] == ["gdi_current"]
    assert result["profiles"]["healthdcat_r8"]["conformant"] is False
    assert conformance.evaluate(r8_dataset(), ["gdi_current", "healthdcat_r8"], rules)["conformant_profiles"] == [
        "gdi_current",
        "healthdcat_r8",
    ]


def test_a_profile_without_rules_stays_satisfied_when_there_is_no_layer(conformance):
    result = conformance.evaluate({}, ["gdi_current"], {"gdi_current": None})
    assert result["access_layer"] is None and result["conformant_profiles"] == ["gdi_current"]


def test_the_dataset_is_not_changed(conformance, r8_rules):
    dataset = non_public_dataset()
    before = copy.deepcopy(dataset)
    evaluate(conformance, r8_rules, dataset)
    assert dataset == before


# --- the shipped file ----------------------------------------------------------------


def test_public_and_restricted_share_ten_mandatory_properties_and_non_public_adds_four(r8_rules):
    labels = {layer: [rule["property"] for rule in body["mandatory"]] for layer, body in r8_rules["layers"].items()}
    assert len(labels["PUBLIC"]) == len(labels["RESTRICTED"]) == 10
    assert labels["PUBLIC"] == labels["RESTRICTED"]
    assert set(labels["NON_PUBLIC"]) - set(labels["PUBLIC"]) == {"contact point", "keyword", "provenance", "type"}
    assert set(labels["PUBLIC"]) <= set(labels["NON_PUBLIC"])


def test_every_field_a_property_names_is_a_field_of_the_r8_schema(generator, r8_rules):
    schema_fields = {f["field_name"] for f in generator.build_schema(["healthdcat_r8"]).schema["dataset_fields"]}
    named = {field for layer in r8_rules["layers"].values() for rule in layer["mandatory"] for field in rule["fields"]}
    assert named - schema_fields - CORE_FIELDS == set()


def test_the_file_records_which_rules_it_was_generated_from(r8_rules):
    assert r8_rules["source"]["file"] == "healthdcat-cardinality-rules.json"
    assert len(r8_rules["source"]["sha256"]) == 64


# --- distributions and dataset series -------------------------------------------------


LAW = ["http://data.europa.eu/eli/reg/2025/327/oj"]


def evaluate_class(conformance, r8_rules, record, kind, profiles=("healthdcat_r8",), rules=None):
    return conformance.evaluate_class(record, list(profiles), rules or {"healthdcat_r8": r8_rules}, kind)["profiles"]["healthdcat_r8"]


@pytest.mark.parametrize("kind", ["distribution", "series"])
def test_a_distribution_or_series_with_applicable_legislation_conforms(conformance, r8_rules, kind):
    result = evaluate_class(conformance, r8_rules, {"applicable_legislation": LAW}, kind)

    assert result == {"conformant": True, "mandatory": 1, "missing": []}


@pytest.mark.parametrize("kind", ["distribution", "series"])
@pytest.mark.parametrize("value", [None, "", [], [""], "[]", [{}], "  "])
def test_a_distribution_or_series_without_applicable_legislation_names_what_is_missing(conformance, r8_rules, kind, value):
    result = evaluate_class(conformance, r8_rules, {"applicable_legislation": value}, kind)

    assert result["conformant"] is False
    assert missing(result) == {"applicable legislation"}


def test_the_class_rules_do_not_depend_on_an_access_layer(conformance, r8_rules):
    for rights in (PUBLIC, RESTRICTED, NON_PUBLIC, None, "nonsense"):
        record = {"access_rights": rights, "applicable_legislation": LAW}
        assert evaluate_class(conformance, r8_rules, record, "distribution")["conformant"] is True


def test_a_profile_without_class_rules_is_satisfied_by_every_distribution(conformance, r8_rules):
    result = conformance.evaluate_class({}, ["gdi_current", "healthdcat_r8"], {"gdi_current": None, "healthdcat_r8": r8_rules}, "distribution")

    assert result["profiles"]["gdi_current"] == {"conformant": True, "mandatory": 0, "missing": []}
    assert result["conformant_profiles"] == ["gdi_current"]


def test_a_pack_with_layer_rules_but_no_class_rules_is_satisfied(conformance, r8_rules):
    dataset_only = {key: value for key, value in r8_rules.items() if key != "classes"}

    result = evaluate_class(conformance, r8_rules, {}, "series", rules={"healthdcat_r8": dataset_only})

    assert result == {"conformant": True, "mandatory": 0, "missing": []}


def test_a_kind_the_rules_do_not_know_has_no_mandatory_properties(conformance, r8_rules):
    assert evaluate_class(conformance, r8_rules, {}, "data service")["conformant"] is True


@pytest.mark.parametrize("record", [None, "text", [], 5, ["a"]])
def test_whatever_a_record_is_it_gives_an_answer_and_not_an_error(conformance, r8_rules, record):
    assert evaluate_class(conformance, r8_rules, record, "distribution")["conformant"] is False


def test_the_class_rules_name_fields_of_the_r8_schemas(generator, r8_rules):
    from conftest import PACKAGE_DIR
    import yaml

    resource_fields = {f["field_name"] for f in generator.build_schema(["healthdcat_r8"]).schema["resource_fields"]}
    series_fields = {
        f["field_name"]
        for f in yaml.safe_load((PACKAGE_DIR / "scheming" / "schemas" / "dataset_series_r8.yaml").read_text(encoding="utf-8"))[
            "dataset_fields"
        ]
    }
    named = lambda kind: {field for rule in r8_rules["classes"][kind]["mandatory"] for field in rule["fields"]}  # noqa: E731

    assert named("distribution") - resource_fields == set()
    assert named("series") - series_fields == set()


def test_the_shipped_file_has_exactly_the_distribution_and_series_classes(r8_rules):
    assert set(r8_rules["classes"]) == {"distribution", "series"}
    assert all(body["source"].startswith("SHACL") for body in r8_rules["classes"].values())
