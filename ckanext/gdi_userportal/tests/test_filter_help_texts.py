# SPDX-FileCopyrightText: 2026 Health-RI
#
# SPDX-License-Identifier: Apache-2.0

from unittest.mock import MagicMock, patch

import pytest

from ckanext.gdi_userportal.logic.action.get import gdi_filter_help_texts_show


def _schema():
    return {
        "dataset_fields": [
            {
                "field_name": "title_translated",
                "facet_key": "title",
                "help_text": {
                    "en": "A descriptive title for the dataset.",
                    "nl": "Een beschrijvende titel voor de dataset.",
                },
                "filter_help_text": {
                    "en": "Use this filter to search datasets by title.",
                    "nl": "Gebruik deze filter om datasets op titel te zoeken.",
                },
            },
            {
                "field_name": "theme",
                "facet_key": "theme",
            },
        ]
    }


def _dataset_series_schema():
    return {
        "dataset_fields": [
            {
                "field_name": "title_translated",
                "facet_key": "title",
                "help_text": {
                    "en": "A descriptive title for the dataset series in each language.",
                    "nl": "Een beschrijvende titel voor de datasetreeks in elke taal.",
                },
                "filter_help_text": {
                    "en": "Use this filter to search dataset series by title.",
                    "nl": "Gebruik deze filter om datasetreeksen op titel te zoeken.",
                },
            }
        ]
    }


def _call_action(data_dict=None, language="en"):
    schema_show = MagicMock(return_value=_schema())

    with patch(
        "ckanext.gdi_userportal.logic.action.get.toolkit.get_action",
        return_value=schema_show,
    ), patch(
        "ckanext.gdi_userportal.logic.action.get.get_request_language",
        return_value=language,
    ):
        result = gdi_filter_help_texts_show({}, data_dict or {})

    schema_show.assert_called_once_with({}, {"type": "dataset"})
    return result


def test_gdi_filter_help_texts_show_returns_english_help_text():
    result = _call_action(language="en")

    assert result == {"title": "Use this filter to search datasets by title."}


def test_gdi_filter_help_texts_show_returns_dutch_help_text():
    result = _call_action(language="nl")

    assert result == {"title": "Gebruik deze filter om datasets op titel te zoeken."}


@pytest.mark.parametrize("language", [None, "", "de"])
def test_gdi_filter_help_texts_show_falls_back_to_english(language):
    result = _call_action(language=language)

    assert result == {"title": "Use this filter to search datasets by title."}


def test_gdi_filter_help_texts_show_filters_requested_keys_from_json_string():
    result = _call_action({"keys": '["theme"]'})

    assert result == {}


def test_gdi_filter_help_texts_show_filters_requested_keys_from_list():
    result = _call_action({"keys": ["title"]}, language="nl")

    assert result == {"title": "Gebruik deze filter om datasets op titel te zoeken."}


def test_gdi_filter_help_texts_show_uses_requested_dataset_type():
    schema_show = MagicMock(return_value=_schema())

    with patch(
        "ckanext.gdi_userportal.logic.action.get.toolkit.get_action",
        return_value=schema_show,
    ), patch(
        "ckanext.gdi_userportal.logic.action.get.get_request_language",
        return_value="en",
    ):
        gdi_filter_help_texts_show({}, {"type": "dataset_series"})

    schema_show.assert_called_once_with({}, {"type": "dataset_series"})


def test_gdi_filter_help_texts_show_returns_dataset_series_help_text():
    schema_show = MagicMock(return_value=_dataset_series_schema())

    with patch(
        "ckanext.gdi_userportal.logic.action.get.toolkit.get_action",
        return_value=schema_show,
    ), patch(
        "ckanext.gdi_userportal.logic.action.get.get_request_language",
        return_value="nl",
    ):
        result = gdi_filter_help_texts_show({}, {"type": "dataset_series"})

    assert result == {
        "title": "Gebruik deze filter om datasetreeksen op titel te zoeken."
    }
