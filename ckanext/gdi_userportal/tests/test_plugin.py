# SPDX-FileCopyrightText: 2024 PNED G.I.E.
#
# SPDX-License-Identifier: Apache-2.0

"""
Tests for plugin.py.

Tests are written using the pytest library (https://docs.pytest.org), and you
should read the testing guidelines in the CKAN docs:
https://docs.ckan.org/en/2.9/contributing/testing.html

To write tests for your extension you should install the pytest-ckan package:

    pip install pytest-ckan

This will allow you to use CKAN specific fixtures on your tests.

For instance, if your test involves database access you can use `clean_db` to
reset the database:

    import pytest

    from ckan.tests import factories

    @pytest.mark.usefixtures("clean_db")
    def test_some_action():

        dataset = factories.Dataset()

        # ...

For functional tests that involve requests to the application, you can use the
`app` fixture:

    from ckan.plugins import toolkit

    def test_some_endpoint(app):

        url = toolkit.url_for('myblueprint.some_endpoint')

        response = app.get(url)

        assert response.status_code == 200


To temporary patch the CKAN configuration for the duration of a test you can use:

    import pytest

    @pytest.mark.ckan_config("ckanext.myext.some_key", "some_value")
    def test_some_action():
        pass
"""
import json
from unittest.mock import MagicMock, patch

import pytest


@pytest.mark.parametrize(
    "in_series_value, expected_ids",
    [
        (None, []),
        ("", []),
        (["id1", "id2"], ["id1", "id2"]),
        ('["id1", "id2"]', ["id1", "id2"]),
        ('"single-id"', ["single-id"]),
        ("not-json", ["not-json"]),
    ],
)
def test_parse_series_ids_handles_various_inputs(in_series_value, expected_ids):
    plugin_instance = plugin.GdiUserPortalPlugin()

    result = plugin_instance._parse_series_ids(in_series_value)

    assert result == expected_ids


@pytest.mark.parametrize("in_series_value", [None, ""])
def test_before_dataset_index_does_not_set_series_vocab_fields_for_empty_in_series(
    in_series_value,
):
    plugin_instance = plugin.GdiUserPortalPlugin()

    result = plugin_instance.before_dataset_index({"in_series": in_series_value})

    assert "vocab_in_series" not in result
    assert "vocab_in_series_name" not in result
    assert "vocab_in_series_title" not in result

import ckanext.gdi_userportal.plugin as plugin


@pytest.mark.parametrize(
    "field, values",
    [
        ("code_values", ["http://www.wikidata.org/entity/Q12125"]),
        ("coding_system", ["https://www.wikidata.org/entity/P494"]),
        ("health_category", ["http://example.org/health-category/1"]),
        ("alternate_identifier", ["urn:uuid:example"]),
    ],
)
def test_before_dataset_index_normalizes_multi_value_fields(field, values):
    plugin_instance = plugin.GdiUserPortalPlugin()
    json_payload = json.dumps(values)
    input_data = {f"extras_{field}": json_payload}

    result = plugin_instance.before_dataset_index(input_data.copy())

    assert result[field] == values
    assert f"extras_{field}" not in result


def test_before_dataset_index_adds_translated_search_fields():
    plugin_instance = plugin.GdiUserPortalPlugin()
    input_data = {
        "extras_conforms_to": json.dumps(["http://example.org/spec"]),
        "extras_code_values": json.dumps(["http://www.wikidata.org/entity/Q12125"]),
        "extras_coding_system": json.dumps(["https://www.wikidata.org/entity/P494"]),
    }

    translation_rows = [
        {
            "term": "http://example.org/spec",
            "term_translation": "Specification",
            "lang_code": "en",
        },
        {
            "term": "http://example.org/spec",
            "term_translation": "Specificatie",
            "lang_code": "nl",
        },
        {
            "term": "http://www.wikidata.org/entity/Q12125",
            "term_translation": "Disease",
            "lang_code": "en",
        },
        {
            "term": "https://www.wikidata.org/entity/P494",
            "term_translation": "ICD-10 identifier",
            "lang_code": "en",
        },
    ]

    translation_show = MagicMock(return_value=translation_rows)

    with patch(
        "ckanext.gdi_userportal.plugin.toolkit.get_action",
        side_effect=lambda action_name: translation_show
        if action_name == "term_translation_show"
        else MagicMock(),
    ):
        result = plugin_instance.before_dataset_index(input_data.copy())

    translation_show.assert_called_once_with(
        {},
        {
            "terms": [
                "http://example.org/spec",
                "http://www.wikidata.org/entity/Q12125",
                "https://www.wikidata.org/entity/P494",
            ]
        },
    )
    assert result["vocab_conforms_to_search"] == [
        "http://example.org/spec",
        "Specification",
        "Specificatie",
    ]
    assert result["vocab_code_values_search"] == [
        "http://www.wikidata.org/entity/Q12125",
        "Disease",
    ]
    assert result["vocab_coding_system_search"] == [
        "https://www.wikidata.org/entity/P494",
        "ICD-10 identifier",
    ]


def test_before_dataset_index_keeps_raw_values_when_translations_are_missing():
    plugin_instance = plugin.GdiUserPortalPlugin()
    input_data = {
        "extras_code_values": json.dumps(["http://www.wikidata.org/entity/Q12125"]),
    }

    translation_show = MagicMock(return_value=[])

    with patch(
        "ckanext.gdi_userportal.plugin.toolkit.get_action",
        side_effect=lambda action_name: translation_show
        if action_name == "term_translation_show"
        else MagicMock(),
    ):
        result = plugin_instance.before_dataset_index(input_data.copy())

    assert result["vocab_code_values_search"] == [
        "http://www.wikidata.org/entity/Q12125"
    ]


def test_before_dataset_index_deduplicates_terms_and_translations():
    plugin_instance = plugin.GdiUserPortalPlugin()
    input_data = {
        "extras_code_values": json.dumps(
            [
                "http://www.wikidata.org/entity/Q12125",
                "http://www.wikidata.org/entity/Q12125",
            ]
        ),
    }

    translation_show = MagicMock(
        return_value=[
            {
                "term": "http://www.wikidata.org/entity/Q12125",
                "term_translation": "Disease",
                "lang_code": "en",
            },
            {
                "term": "http://www.wikidata.org/entity/Q12125",
                "term_translation": "Disease",
                "lang_code": "nl",
            },
        ]
    )

    with patch(
        "ckanext.gdi_userportal.plugin.toolkit.get_action",
        side_effect=lambda action_name: translation_show
        if action_name == "term_translation_show"
        else MagicMock(),
    ):
        result = plugin_instance.before_dataset_index(input_data.copy())

    assert result["vocab_code_values_search"] == [
        "http://www.wikidata.org/entity/Q12125",
        "Disease",
    ]


def test_before_dataset_index_indexes_resource_and_access_service_conforms_to():
    plugin_instance = plugin.GdiUserPortalPlugin()
    input_data = {
        "res_extras_conforms_to": json.dumps(["http://example.org/resource-standard"]),
        "res_extras_access_services": json.dumps(
            [{"conforms_to": ["http://example.org/service-standard"]}]
        ),
    }

    translation_show = MagicMock(
        return_value=[
            {
                "term": "http://example.org/resource-standard",
                "term_translation": "Resource standard",
                "lang_code": "en",
            },
            {
                "term": "http://example.org/service-standard",
                "term_translation": "Service standard",
                "lang_code": "en",
            },
        ]
    )

    with patch(
        "ckanext.gdi_userportal.plugin.toolkit.get_action",
        side_effect=lambda action_name: translation_show
        if action_name == "term_translation_show"
        else MagicMock(),
    ):
        result = plugin_instance.before_dataset_index(input_data.copy())

    assert result["vocab_conforms_to_search"] == [
        "http://example.org/resource-standard",
        "Resource standard",
        "http://example.org/service-standard",
        "Service standard",
    ]


def test_before_dataset_index_handles_malformed_resource_access_services():
    plugin_instance = plugin.GdiUserPortalPlugin()
    input_data = {
        "extras_conforms_to": "http://example.org/spec",
        "res_extras_access_services": "not-json",
    }

    translation_show = MagicMock(
        return_value=[
            {
                "term": "http://example.org/spec",
                "term_translation": "Specification",
                "lang_code": "en",
            }
        ]
    )

    with patch(
        "ckanext.gdi_userportal.plugin.toolkit.get_action",
        side_effect=lambda action_name: translation_show
        if action_name == "term_translation_show"
        else MagicMock(),
    ):
        result = plugin_instance.before_dataset_index(input_data.copy())

    assert result["conforms_to"] == "http://example.org/spec"
    assert result["vocab_conforms_to_search"] == [
        "http://example.org/spec",
        "Specification",
    ]


def test_dataset_facets_include_dataset_series_title():
    plugin_instance = plugin.GdiUserPortalPlugin()

    result = plugin_instance.dataset_facets(
        {"tags": "Tags", "groups": "Groups"}, "dataset"
    )

    assert "groups" not in result
    assert result["vocab_in_series_title"] == "Dataset series"
    assert result["tags"] == "Tags"


def test_before_dataset_index_adds_dataset_series_titles():
    plugin_instance = plugin.GdiUserPortalPlugin()
    package_show = MagicMock(
        return_value={"name": "series-name", "title": "Series Title"}
    )

    with patch(
        "ckanext.gdi_userportal.plugin.toolkit.get_action",
        return_value=package_show,
    ):
        result = plugin_instance.before_dataset_index({"in_series": "series-id"})

    assert result["vocab_in_series"] == ["series-id"]
    assert result["vocab_in_series_name"] == ["series-name"]
    assert result["vocab_in_series_title"] == ["Series Title"]


def test_before_dataset_index_ignores_errors_from_package_show():
    plugin_instance = plugin.GdiUserPortalPlugin()

    def package_show(context, data_dict):
        series_id = data_dict["id"]
        if series_id == "series-error-notfound":
            raise plugin.toolkit.ObjectNotFound("series not found")
        if series_id == "series-error-notauthorized":
            raise plugin.toolkit.NotAuthorized("not authorized to read series")

        return {
            "name": f"{series_id}-name",
            "title": f"{series_id}-title",
        }

    with patch(
        "ckanext.gdi_userportal.plugin.toolkit.get_action",
        return_value=package_show,
    ):
        result = plugin_instance.before_dataset_index(
            {
                "in_series": [
                    "series-error-notfound",
                    "series-ok",
                    "series-error-notauthorized",
                ]
            }
        )

    assert result["vocab_in_series"] == [
        "series-error-notfound",
        "series-ok",
        "series-error-notauthorized",
    ]
    assert result["vocab_in_series_name"] == ["series-ok-name"]
    assert result["vocab_in_series_title"] == ["series-ok-title"]


def test_before_dataset_index_handles_partial_series_metadata():
    plugin_instance = plugin.GdiUserPortalPlugin()

    def package_show(context, data_dict):
        series_id = data_dict["id"]
        if series_id == "series-with-name-only":
            return {"name": "name-only-series"}
        if series_id == "series-with-title-only":
            return {"title": "Title Only Series"}
        return {}

    with patch(
        "ckanext.gdi_userportal.plugin.toolkit.get_action",
        return_value=package_show,
    ):
        result = plugin_instance.before_dataset_index(
            {
                "in_series": [
                    "series-with-name-only",
                    "series-with-title-only",
                ]
            }
        )

    assert result["vocab_in_series"] == [
        "series-with-name-only",
        "series-with-title-only",
    ]
    assert result["vocab_in_series_name"] == ["name-only-series"]
    assert result["vocab_in_series_title"] == ["Title Only Series"]


def test_before_dataset_index_deduplicates_series_metadata():
    plugin_instance = plugin.GdiUserPortalPlugin()

    def package_show(context, data_dict):
        series_id = data_dict["id"]
        if series_id in ("series-1", "series-1-duplicate"):
            return {"name": "series-1-name", "title": "Series 1"}
        if series_id == "series-2":
            return {"name": "series-2-name", "title": "Series 2"}
        return {}

    with patch(
        "ckanext.gdi_userportal.plugin.toolkit.get_action",
        return_value=package_show,
    ):
        result = plugin_instance.before_dataset_index(
            {
                "in_series": [
                    "series-1",
                    "series-1",
                    "series-1-duplicate",
                    "series-2",
                ]
            }
        )

    assert result["vocab_in_series"] == [
        "series-1",
        "series-1",
        "series-1-duplicate",
        "series-2",
    ]
    assert result["vocab_in_series_name"] == ["series-1-name", "series-2-name"]
    assert result["vocab_in_series_title"] == ["Series 1", "Series 2"]


def test_get_commands_returns_cli_commands():
    """Test that get_commands returns the CLI command group."""
    plugin_instance = plugin.GdiUserPortalPlugin()
    
    commands = plugin_instance.get_commands()
    
    assert commands is not None
    assert isinstance(commands, list)
    assert len(commands) > 0
    # Verify the command group is the gdi_userportal command
    assert commands[0].name == "gdi-userportal"


class TestMergeTagsTranslatedForIndexing:
    """Tests for _merge_tags_translated_for_indexing method."""

    def test_no_tags_translated_returns_unchanged(self):
        """When no tags_translated field exists, data is unchanged."""
        plugin_instance = plugin.GdiUserPortalPlugin()
        input_data = {"tags": ["existing-tag"], "title": "Test"}

        result = plugin_instance._merge_tags_translated_for_indexing(input_data.copy())

        assert result["tags"] == ["existing-tag"]
        assert result["title"] == "Test"

    def test_merges_tags_translated_into_tags(self):
        """Tags from tags_translated are merged into tags field."""
        plugin_instance = plugin.GdiUserPortalPlugin()
        input_data = {
            "tags": ["harvested-tag"],
            "extras_tags_translated": json.dumps({
                "en": ["manual-tag-en"],
                "nl": ["manual-tag-nl"]
            })
        }

        result = plugin_instance._merge_tags_translated_for_indexing(input_data.copy())

        assert "harvested-tag" in result["tags"]
        assert "manual-tag-en" in result["tags"]
        assert "manual-tag-nl" in result["tags"]

    def test_removes_duplicates(self):
        """Duplicate tags are not added twice."""
        plugin_instance = plugin.GdiUserPortalPlugin()
        input_data = {
            "tags": ["same-tag", "unique-tag"],
            "extras_tags_translated": json.dumps({
                "en": ["same-tag", "another-tag"]
            })
        }

        result = plugin_instance._merge_tags_translated_for_indexing(input_data.copy())

        assert result["tags"].count("same-tag") == 1
        assert "unique-tag" in result["tags"]
        assert "another-tag" in result["tags"]

    def test_handles_empty_tags_list(self):
        """Works when existing tags is empty list."""
        plugin_instance = plugin.GdiUserPortalPlugin()
        input_data = {
            "tags": [],
            "extras_tags_translated": json.dumps({
                "en": ["translated-only"]
            })
        }

        result = plugin_instance._merge_tags_translated_for_indexing(input_data.copy())

        assert result["tags"] == ["translated-only"]

    def test_handles_no_existing_tags(self):
        """Works when tags field doesn't exist."""
        plugin_instance = plugin.GdiUserPortalPlugin()
        input_data = {
            "extras_tags_translated": json.dumps({
                "en": ["new-tag"]
            })
        }

        result = plugin_instance._merge_tags_translated_for_indexing(input_data.copy())

        assert result["tags"] == ["new-tag"]

    def test_handles_invalid_json(self):
        """Invalid JSON in tags_translated returns unchanged."""
        plugin_instance = plugin.GdiUserPortalPlugin()
        input_data = {
            "tags": ["existing"],
            "extras_tags_translated": "not valid json"
        }

        result = plugin_instance._merge_tags_translated_for_indexing(input_data.copy())

        assert result["tags"] == ["existing"]

    def test_handles_non_dict_tags_translated(self):
        """Non-dict tags_translated returns unchanged."""
        plugin_instance = plugin.GdiUserPortalPlugin()
        input_data = {
            "tags": ["existing"],
            "extras_tags_translated": json.dumps(["not", "a", "dict"])
        }

        result = plugin_instance._merge_tags_translated_for_indexing(input_data.copy())

        assert result["tags"] == ["existing"]

    def test_filters_blank_tags(self):
        """Blank and whitespace-only tags are filtered out."""
        plugin_instance = plugin.GdiUserPortalPlugin()
        input_data = {
            "tags": ["valid"],
            "extras_tags_translated": json.dumps({
                "en": ["", "  ", "valid-translated"]
            })
        }

        result = plugin_instance._merge_tags_translated_for_indexing(input_data.copy())

        assert "" not in result["tags"]
        assert "  " not in result["tags"]
        assert "valid" in result["tags"]
        assert "valid-translated" in result["tags"]

    def test_trims_whitespace(self):
        """Whitespace around tags is trimmed."""
        plugin_instance = plugin.GdiUserPortalPlugin()
        input_data = {
            "tags": [],
            "extras_tags_translated": json.dumps({
                "en": ["  spaced tag  "]
            })
        }

        result = plugin_instance._merge_tags_translated_for_indexing(input_data.copy())

        assert "spaced tag" in result["tags"]
        assert "  spaced tag  " not in result["tags"]

    def test_handles_tags_as_string(self):
        """Works when existing tags is a string instead of list."""
        plugin_instance = plugin.GdiUserPortalPlugin()
        input_data = {
            "tags": "single-tag",
            "extras_tags_translated": json.dumps({
                "en": ["translated-tag"]
            })
        }

        result = plugin_instance._merge_tags_translated_for_indexing(input_data.copy())

        assert "single-tag" in result["tags"]
        assert "translated-tag" in result["tags"]
