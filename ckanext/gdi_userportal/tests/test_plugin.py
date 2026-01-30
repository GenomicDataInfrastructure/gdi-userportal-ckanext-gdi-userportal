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
