# SPDX-FileCopyrightText: 2026 Health-RI
#
# SPDX-License-Identifier: Apache-2.0

from unittest.mock import MagicMock, patch

import pytest

from ckanext.gdi_userportal.logic.action.get import gdi_filter_help_texts_show


DATASET_FILTER_CASES = [
    (
        "title_translated",
        "title",
        "Use this filter to search datasets by title.",
        "Gebruik deze filter om datasets op titel te zoeken.",
    ),
    (
        "tags_translated",
        "tags",
        "Use this filter to search datasets by keywords.",
        "Gebruik deze filter om datasets op trefwoorden te zoeken.",
    ),
    (
        "access_rights",
        "access_rights",
        "Use this filter to search datasets by access rights.",
        "Gebruik deze filter om datasets op toegangsrechten te zoeken.",
    ),
    (
        "alternate_identifier",
        "alternate_identifier",
        "Use this filter to search datasets by other identifiers.",
        "Gebruik deze filter om datasets op andere identificatoren te zoeken.",
    ),
    (
        "theme",
        "theme",
        "Use this filter to search datasets by theme.",
        "Gebruik deze filter om datasets op thema te zoeken.",
    ),
    (
        "language",
        "language",
        "Use this filter to search datasets by language.",
        "Gebruik deze filter om datasets op taal te zoeken.",
    ),
    (
        "conforms_to",
        "conforms_to",
        "Use this filter to search datasets by conformance specification.",
        "Gebruik deze filter om datasets op specificatie te zoeken.",
    ),
    (
        "is_referenced_by",
        "is_referenced_by",
        "Use this filter to search datasets by related references.",
        "Gebruik deze filter om datasets op verwijzingen te zoeken.",
    ),
    (
        "code_values",
        "code_values",
        "Use this filter to search datasets by code values.",
        "Gebruik deze filter om datasets op codewaarden te zoeken.",
    ),
    (
        "coding_system",
        "coding_system",
        "Use this filter to search datasets by coding system.",
        "Gebruik deze filter om datasets op coderingssysteem te zoeken.",
    ),
    (
        "health_theme",
        "health_theme",
        "Use this filter to search datasets by health theme.",
        "Gebruik deze filter om datasets op gezondheidsthema te zoeken.",
    ),
    (
        "legal_basis",
        "legal_basis",
        "Use this filter to search datasets by legal basis.",
        "Gebruik deze filter om datasets op rechtsgrondslag te zoeken.",
    ),
    (
        "min_typical_age",
        "typical_age",
        "Use this filter to search datasets by typical age.",
        "Gebruik deze filter om datasets op typische leeftijd te zoeken.",
    ),
    (
        "number_of_records",
        "number_of_records",
        "Use this filter to search datasets by number of records.",
        "Gebruik deze filter om datasets op aantal records te zoeken.",
    ),
    (
        "personal_data",
        "personal_data",
        "Use this filter to search datasets by personal data elements.",
        "Gebruik deze filter om datasets op persoonsgegevens te zoeken.",
    ),
    (
        "issued",
        "issued",
        "Use this filter to search datasets by release date.",
        "Gebruik deze filter om datasets op releasedatum te zoeken.",
    ),
    (
        "modified",
        "modified",
        "Use this filter to search datasets by modification date.",
        "Gebruik deze filter om datasets op wijzigingsdatum te zoeken.",
    ),
    (
        "frequency",
        "frequency",
        "Use this filter to search datasets by publication frequency.",
        "Gebruik deze filter om datasets op publicatiefrequentie te zoeken.",
    ),
]

DATASET_SERIES_FILTER_CASES = [
    (
        "title_translated",
        "title",
        "Use this filter to search dataset series by title.",
        "Gebruik deze filter om datasetreeksen op titel te zoeken.",
    ),
    (
        "frequency",
        "frequency",
        "Use this filter to search dataset series by frequency.",
        "Gebruik deze filter om datasetreeksen op frequentie te zoeken.",
    ),
    (
        "modified",
        "modified",
        "Use this filter to search dataset series by modification date.",
        "Gebruik deze filter om datasetreeksen op wijzigingsdatum te zoeken.",
    ),
    (
        "issued",
        "issued",
        "Use this filter to search dataset series by release date.",
        "Gebruik deze filter om datasetreeksen op releasedatum te zoeken.",
    ),
]


def _schema(cases=DATASET_FILTER_CASES):
    return {
        "dataset_fields": [
            {
                "field_name": field_name,
                "facet_key": facet_key,
                "filter_help_text": {
                    "en": help_text_en,
                    "nl": help_text_nl,
                },
            }
            for field_name, facet_key, help_text_en, help_text_nl in cases
        ]
    }


def _dataset_series_schema():
    return _schema(DATASET_SERIES_FILTER_CASES)


def _call_action(data_dict=None, language="en", schema=None):
    schema_show = MagicMock(return_value=schema or _schema())
    request_data = data_dict or {}
    dataset_type = request_data.get("type", "dataset")

    with patch(
        "ckanext.gdi_userportal.logic.action.get.toolkit.get_action",
        return_value=schema_show,
    ), patch(
        "ckanext.gdi_userportal.logic.action.get.get_request_language",
        return_value=language,
    ):
        result = gdi_filter_help_texts_show({}, request_data)

    schema_show.assert_called_once_with({}, {"type": dataset_type})
    return result


@pytest.mark.parametrize("field_name, facet_key, expected_en, expected_nl", DATASET_FILTER_CASES)
@pytest.mark.parametrize("language", ["en", "nl"])
def test_gdi_filter_help_texts_show_returns_dataset_help_texts(
    field_name, facet_key, expected_en, expected_nl, language
):
    expected = expected_en if language == "en" else expected_nl

    result = _call_action({"keys": [facet_key]}, language=language)

    assert result == {facet_key: expected}


@pytest.mark.parametrize(
    "field_name, facet_key, expected_en, expected_nl",
    DATASET_SERIES_FILTER_CASES,
)
@pytest.mark.parametrize("language", ["en", "nl"])
def test_gdi_filter_help_texts_show_returns_dataset_series_help_texts(
    field_name, facet_key, expected_en, expected_nl, language
):
    expected = expected_en if language == "en" else expected_nl

    result = _call_action(
        {"type": "dataset_series", "keys": [facet_key]},
        language=language,
        schema=_dataset_series_schema(),
    )

    assert result == {facet_key: expected}


@pytest.mark.parametrize("language", [None, "", "de"])
def test_gdi_filter_help_texts_show_falls_back_to_english(language):
    result = _call_action({"keys": ["theme"]}, language=language)

    assert result == {
        "theme": "Use this filter to search datasets by theme.",
    }


def test_gdi_filter_help_texts_show_filters_requested_keys_from_json_string():
    result = _call_action({"keys": '["theme", "unknown"]'})

    assert result == {
        "theme": "Use this filter to search datasets by theme.",
    }


@pytest.mark.parametrize("keys", ["[]", [], ["   "], [None]])
def test_gdi_filter_help_texts_show_empty_requested_keys_returns_no_keys(keys):
    result = _call_action({"keys": keys})

    assert result == {}


def test_gdi_filter_help_texts_show_uses_requested_dataset_type():
    schema_show = MagicMock(return_value=_dataset_series_schema())

    with patch(
        "ckanext.gdi_userportal.logic.action.get.toolkit.get_action",
        return_value=schema_show,
    ), patch(
        "ckanext.gdi_userportal.logic.action.get.get_request_language",
        return_value="en",
    ):
        gdi_filter_help_texts_show({}, {"type": "dataset_series"})

    schema_show.assert_called_once_with({}, {"type": "dataset_series"})
