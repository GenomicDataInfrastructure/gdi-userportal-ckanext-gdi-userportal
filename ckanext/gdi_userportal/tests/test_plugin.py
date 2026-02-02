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

import pytest

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
