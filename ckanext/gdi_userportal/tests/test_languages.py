# SPDX-FileCopyrightText: 2026 Stichting Health-RI
#
# SPDX-License-Identifier: Apache-2.0

from ckanext.gdi_userportal.languages import (
    fall_back_to_available_languages,
    without_empty_languages,
)

SCHEMA = {
    "dataset_fields": [
        {"field_name": "title_translated", "preset": "fluent_core_translated"},
        {"field_name": "tags_translated", "validators": "fluent_tags"},
        {"field_name": "population_coverage", "preset": "fluent_markdown"},
        {"field_name": "identifier"},
        {
            "field_name": "publisher",
            "repeating_subfields": [
                {"field_name": "name"},
                {"field_name": "name_translated", "preset": "fluent_text"},
            ],
        },
    ],
    "resource_fields": [
        {"field_name": "description_translated", "preset": "fluent_text"},
    ],
}


def test_empty_languages_are_dropped():
    assert without_empty_languages({"en": "Title", "nl": ""}) == {"en": "Title"}
    assert without_empty_languages({"en": ["a"], "nl": []}) == {"en": ["a"]}
    assert without_empty_languages({"en": "Title", "nl": "  "}) == {"en": "Title"}


def test_a_map_with_nothing_in_it_stays_a_map():
    assert without_empty_languages({"en": "", "nl": ""}) == {"en": "", "nl": ""}


def test_other_values_are_left_alone():
    assert without_empty_languages("text") == "text"
    assert without_empty_languages(None) is None


def test_fluent_fields_of_a_dataset_fall_back():
    dataset = {
        "title": "Title",
        "title_translated": {"en": "Title", "nl": ""},
        "tags_translated": {"en": ["oncology"], "nl": []},
        "population_coverage": {"en": "Adults", "nl": ""},
        "identifier": "abc",
    }
    result = fall_back_to_available_languages(dataset, SCHEMA)
    assert result["title_translated"] == {"en": "Title"}
    assert result["tags_translated"] == {"en": ["oncology"]}
    assert result["population_coverage"] == {"en": "Adults"}
    assert result["identifier"] == "abc"


def test_nested_and_resource_fields_fall_back():
    dataset = {
        "publisher": [{"name": "Registry", "name_translated": {"en": "Registry", "nl": ""}}],
        "resources": [{"description_translated": {"en": "", "nl": "Beschrijving"}}],
    }
    result = fall_back_to_available_languages(dataset, SCHEMA)
    assert result["publisher"][0]["name_translated"] == {"en": "Registry"}
    assert result["resources"][0]["description_translated"] == {"nl": "Beschrijving"}


def test_an_empty_core_field_takes_the_language_that_exists():
    dataset = {"title": "", "title_translated": {"en": "", "nl": "Titel"}}
    result = fall_back_to_available_languages(dataset, SCHEMA)
    assert result["title"] == "Titel"
    assert result["title_translated"] == {"nl": "Titel"}


def test_a_filled_core_field_is_kept():
    dataset = {"title": "Title", "title_translated": {"en": "Title", "nl": "Titel"}}
    result = fall_back_to_available_languages(dataset, SCHEMA)
    assert result["title"] == "Title"
    assert result["title_translated"] == {"en": "Title", "nl": "Titel"}


def test_missing_schema_or_odd_values_never_raise():
    assert fall_back_to_available_languages({"a": 1}, None) == {"a": 1}
    odd = {"title_translated": "not a map", "publisher": "not a list", "resources": [None]}
    assert fall_back_to_available_languages(odd, SCHEMA) == odd
