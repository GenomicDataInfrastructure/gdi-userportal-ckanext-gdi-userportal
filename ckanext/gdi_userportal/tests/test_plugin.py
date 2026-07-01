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
from datetime import datetime
from unittest.mock import MagicMock, patch
from urllib.parse import quote

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


def test_before_dataset_index_canonicalizes_http_https_theme_uris():
    plugin_instance = plugin.GdiUserPortalPlugin()
    input_data = {
        "extras_theme": json.dumps(
            [
                "https://publications.europa.eu/resource/authority/data-theme/HEAL",
                "http://publications.europa.eu/resource/authority/data-theme/HEAL",
                "https://publications.europa.eu/resource/authority/data-theme/ENER",
            ]
        )
    }

    result = plugin_instance.before_dataset_index(input_data.copy())

    assert result["theme"] == [
        "http://publications.europa.eu/resource/authority/data-theme/HEAL",
        "http://publications.europa.eu/resource/authority/data-theme/ENER",
    ]


def test_before_dataset_index_keeps_non_publications_theme_uris_unchanged():
    plugin_instance = plugin.GdiUserPortalPlugin()
    input_data = {
        "extras_theme": json.dumps(
            [
                "https://example.org/theme/custom",
                "http://publications.europa.eu/resource/authority/data-theme/HEAL",
            ]
        )
    }

    result = plugin_instance.before_dataset_index(input_data.copy())

    assert result["theme"] == [
        "https://example.org/theme/custom",
        "http://publications.europa.eu/resource/authority/data-theme/HEAL",
    ]


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


def test_before_dataset_index_indexes_qualified_attribution_roles_and_agents():
    plugin_instance = plugin.GdiUserPortalPlugin()
    input_data = {
        "extras_qualified_attribution": json.dumps(
            [
                {
                    "role": "http://example.org/role/processor",
                    "agent": [
                        {"name": "Org A"},
                        {"name": "Org B"},
                    ],
                },
                {
                    "role": "http://example.org/role/controller",
                    "agent": {"name": "Org C"},
                },
            ]
        )
    }

    result = plugin_instance.before_dataset_index(input_data.copy())

    assert result["qualified_attribution"] == [
        {
            "role": "http://example.org/role/processor",
            "agent": [
                {"name": "Org A"},
                {"name": "Org B"},
            ],
        },
        {
            "role": "http://example.org/role/controller",
            "agent": {"name": "Org C"},
        },
    ]
    assert result["vocab_qualified_attribution_role"] == [
        "http://example.org/role/processor",
        "http://example.org/role/controller",
    ]
    assert result["vocab_qualified_attribution_agent_name"] == [
        "Org A",
        "Org B",
        "Org C",
    ]


def test_extract_nested_string_values_flattens_nested_dicts_and_lists():
    plugin_instance = plugin.GdiUserPortalPlugin()

    result = plugin_instance._extract_nested_string_values(
        {
            "primary": "Org A",
            "aliases": [
                "Org B",
                {"secondary": ["Org C", None]},
            ],
            "ignored": 42,
        }
    )

    assert result == ["Org A", "Org B", "Org C"]


@pytest.mark.parametrize(
    "agents, expected",
    [
        (None, []),
        (42, []),
        ("plain-org", ["plain-org"]),
        ('{"name": ["Org D", {"nested": "Org E"}]}', ["Org D", "Org E"]),
    ],
)
def test_parse_qualified_attribution_agent_names_normalizes_inputs(
    agents, expected
):
    plugin_instance = plugin.GdiUserPortalPlugin()

    result = plugin_instance._parse_qualified_attribution_agent_names(agents)

    assert result == expected


@pytest.mark.parametrize(
    "qualified_attribution, expected",
    [
        (123, ([], [])),
        (
            {
                "role": "http://example.org/role/owner",
                "agent": "Org A",
            },
            (
                ["http://example.org/role/owner"],
                ["Org A"],
            ),
        ),
        (
            [
                "skip me",
                {
                    "role": "http://example.org/role/controller",
                    "agent": {
                        "name": {"primary": "Org B", "aliases": ["Org C"]},
                    },
                },
            ],
            (
                ["http://example.org/role/controller"],
                ["Org B", "Org C"],
            ),
        ),
    ],
)
def test_parse_qualified_attribution_handles_mixed_inputs(
    qualified_attribution, expected
):
    plugin_instance = plugin.GdiUserPortalPlugin()

    result = plugin_instance._parse_qualified_attribution(
        {"qualified_attribution": qualified_attribution}
    )

    assert result == expected


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
            {
                "term": 123,  # non-string term, should be ignored
                "term_translation": "Invalid",
                "lang_code": "en",
            },
            {
                "term": "http://www.wikidata.org/entity/Q12125",
                "term_translation": "",  # empty translation, should be ignored
                "lang_code": "en",
            },
            {
                "term": "http://www.wikidata.org/entity/Q12125",
                "term_translation": "   ",  # whitespace-only translation, should be ignored
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

    assert result["vocab_code_values_search"] == [
        "http://www.wikidata.org/entity/Q12125",
        "Disease",
    ]


def test_before_dataset_index_indexes_resource_and_access_service_conforms_to():
    plugin_instance = plugin.GdiUserPortalPlugin()
    input_data = {
        # `extras_*` coverage
        "extras_conforms_to": json.dumps(["http://example.org/spec"]),
        "extras_code_values": json.dumps(["http://www.wikidata.org/entity/Q12125"]),
        "extras_coding_system": json.dumps(["https://www.wikidata.org/entity/P494"]),
        # New coverage for `resources[*].conforms_to` and
        # `resources[*].access_services[*].conforms_to`
        "resources": [
            {
                "conforms_to": ["http://example.org/resource-spec"],
                "access_services": [
                    {
                        "conforms_to": ["http://example.org/access-service-spec"],
                    }
                ],
            }
        ],
    }

    translation_show = MagicMock(
        return_value=[
            {
                "term": "http://example.org/spec",
                "term_translation": "Specification",
                "lang_code": "en",
            },
            {
                "term": "http://example.org/resource-spec",
                "term_translation": "Resource specification",
                "lang_code": "en",
            },
            {
                "term": "http://example.org/access-service-spec",
                "term_translation": "Access service specification",
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
        "http://example.org/spec",
        "Specification",
        "http://example.org/resource-spec",
        "Resource specification",
        "http://example.org/access-service-spec",
        "Access service specification",
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


class TestBeforeDatasetSearchTemporalCoverage:
    def test_returns_unchanged_when_no_temporal_extras(self):
        plugin_instance = plugin.GdiUserPortalPlugin()
        search_params = {"q": "test"}

        result = plugin_instance.before_dataset_search(search_params.copy())

        assert result == search_params
        assert "fq_list" not in result

    def test_adds_fq_for_min_and_max(self):
        plugin_instance = plugin.GdiUserPortalPlugin()
        search_params = {
            "extras": {
                "ext_temporal_min": "2020-01-01",
                "ext_temporal_max": "2021-06-15",
            }
        }

        result = plugin_instance.before_dataset_search(search_params)

        assert result["fq_list"] == [
            "temporal_coverage_range:[2020-01-01T00:00:00Z TO 2021-06-15T00:00:00Z]"
        ]

    def test_adds_fq_with_open_lower_bound(self):
        plugin_instance = plugin.GdiUserPortalPlugin()
        search_params = {"extras": {"ext_temporal_max": "2021-06-15"}}

        result = plugin_instance.before_dataset_search(search_params)

        assert result["fq_list"] == [
            "temporal_coverage_range:[* TO 2021-06-15T00:00:00Z]"
        ]

    def test_adds_fq_with_open_upper_bound(self):
        plugin_instance = plugin.GdiUserPortalPlugin()
        search_params = {"extras": {"ext_temporal_min": "2020-01-01"}}

        result = plugin_instance.before_dataset_search(search_params)

        assert result["fq_list"] == [
            "temporal_coverage_range:[2020-01-01T00:00:00Z TO *]"
        ]

    def test_appends_to_existing_fq_list(self):
        plugin_instance = plugin.GdiUserPortalPlugin()
        search_params = {
            "fq_list": ["res_format:CSV"],
            "extras": {"ext_temporal_min": "2020-01-01"},
        }

        result = plugin_instance.before_dataset_search(search_params)

        assert result["fq_list"] == [
            "res_format:CSV",
            "temporal_coverage_range:[2020-01-01T00:00:00Z TO *]",
        ]

    def test_raises_validation_error_for_invalid_min(self):
        plugin_instance = plugin.GdiUserPortalPlugin()
        search_params = {"extras": {"ext_temporal_min": "not-a-date"}}

        with pytest.raises(plugin.toolkit.ValidationError):
            plugin_instance.before_dataset_search(search_params)

    def test_raises_validation_error_for_invalid_max(self):
        plugin_instance = plugin.GdiUserPortalPlugin()
        search_params = {"extras": {"ext_temporal_max": "not-a-date"}}

        with pytest.raises(plugin.toolkit.ValidationError):
            plugin_instance.before_dataset_search(search_params)

    def test_raises_validation_error_when_min_after_max(self):
        plugin_instance = plugin.GdiUserPortalPlugin()
        search_params = {
            "extras": {
                "ext_temporal_min": "2022-01-01",
                "ext_temporal_max": "2021-01-01",
            }
        }

        with pytest.raises(plugin.toolkit.ValidationError):
            plugin_instance.before_dataset_search(search_params)


class TestToSolrDatetime:
    def test_converts_datetime_object(self):
        plugin_instance = plugin.GdiUserPortalPlugin()

        result = plugin_instance._to_solr_datetime(
            datetime(2020, 1, 1, 12, 30, 0)
        )

        assert result == "2020-01-01T12:30:00Z"

    def test_converts_iso_string(self):
        plugin_instance = plugin.GdiUserPortalPlugin()

        result = plugin_instance._to_solr_datetime("2020-01-01T12:30:00+02:00")

        assert result == "2020-01-01T10:30:00Z"

    def test_returns_none_for_invalid_string(self):
        plugin_instance = plugin.GdiUserPortalPlugin()

        assert plugin_instance._to_solr_datetime("not-a-date") is None

    def test_returns_none_for_empty_value(self):
        plugin_instance = plugin.GdiUserPortalPlugin()

        assert plugin_instance._to_solr_datetime(None) is None
        assert plugin_instance._to_solr_datetime("") is None


class TestBuildTemporalCoverageRanges:
    def test_returns_data_dict_unchanged_when_field_missing(self):
        plugin_instance = plugin.GdiUserPortalPlugin()
        data_dict = {"other_field": "value"}

        result = plugin_instance._build_temporal_coverage_ranges(data_dict)

        assert result == {"other_field": "value"}

    def test_ignores_temporal_coverage_when_json_string_is_invalid(self):
        plugin_instance = plugin.GdiUserPortalPlugin()
        data_dict = {"temporal_coverage": "not-json"}

        result = plugin_instance._build_temporal_coverage_ranges(data_dict)

        assert "temporal_coverage_range" not in result
        assert "temporal_coverage" not in result

    def test_returns_data_dict_unchanged_when_not_a_list(self):
        plugin_instance = plugin.GdiUserPortalPlugin()
        data_dict = {"temporal_coverage": json.dumps({"start": "2020-01-01"})}

        result = plugin_instance._build_temporal_coverage_ranges(data_dict)

        assert "temporal_coverage_range" not in result

    def test_builds_ranges_and_min_max_from_bounded_periods(self):
        plugin_instance = plugin.GdiUserPortalPlugin()
        data_dict = {
            "temporal_coverage": [
                {"start": "2015-01-01", "end": "2016-01-01"},
                {"start": "2018-06-01", "end": "2020-01-01"},
            ]
        }

        result = plugin_instance._build_temporal_coverage_ranges(data_dict)

        assert result["temporal_coverage_range"] == [
            "[2015-01-01T00:00:00Z TO 2016-01-01T00:00:00Z]",
            "[2018-06-01T00:00:00Z TO 2020-01-01T00:00:00Z]",
        ]
        assert result["temporal_coverage_min"] == "2015-01-01T00:00:00Z"
        assert result["temporal_coverage_max"] == "2020-01-01T00:00:00Z"
        assert "temporal_coverage" not in result

    def test_accepts_temporal_coverage_as_json_string(self):
        plugin_instance = plugin.GdiUserPortalPlugin()
        data_dict = {
            "temporal_coverage": json.dumps(
                [{"start": "2015-01-01", "end": "2016-01-01"}]
            )
        }

        result = plugin_instance._build_temporal_coverage_ranges(data_dict)

        assert result["temporal_coverage_range"] == [
            "[2015-01-01T00:00:00Z TO 2016-01-01T00:00:00Z]"
        ]

    def test_open_ended_period_is_included_in_ranges_but_not_min_max(self):
        plugin_instance = plugin.GdiUserPortalPlugin()
        data_dict = {"temporal_coverage": [{"start": "2015-01-01"}]}

        result = plugin_instance._build_temporal_coverage_ranges(data_dict)

        assert result["temporal_coverage_range"] == ["[2015-01-01T00:00:00Z TO *]"]
        assert result["temporal_coverage_min"] == "2015-01-01T00:00:00Z"
        assert "temporal_coverage_max" not in result

    def test_period_without_start_or_end_is_skipped(self):
        plugin_instance = plugin.GdiUserPortalPlugin()
        data_dict = {"temporal_coverage": [{}, {"start": "2015-01-01"}]}

        result = plugin_instance._build_temporal_coverage_ranges(data_dict)

        assert result["temporal_coverage_range"] == ["[2015-01-01T00:00:00Z TO *]"]

    def test_non_dict_period_is_skipped(self):
        plugin_instance = plugin.GdiUserPortalPlugin()
        data_dict = {"temporal_coverage": ["not-a-dict", {"start": "2015-01-01"}]}

        result = plugin_instance._build_temporal_coverage_ranges(data_dict)

        assert result["temporal_coverage_range"] == ["[2015-01-01T00:00:00Z TO *]"]

    def test_no_bounded_periods_results_in_no_range_fields(self):
        plugin_instance = plugin.GdiUserPortalPlugin()
        data_dict = {"temporal_coverage": [{}, "invalid"]}

        result = plugin_instance._build_temporal_coverage_ranges(data_dict)

        assert "temporal_coverage_range" not in result
        assert "temporal_coverage_min" not in result
        assert "temporal_coverage_max" not in result
