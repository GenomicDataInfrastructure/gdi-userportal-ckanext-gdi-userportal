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
from ckanext.gdi_userportal import indexing

# before_dataset_index reads the dataset schema (the solr key of its fields): the one the packs generate
pytestmark = pytest.mark.usefixtures("indexing_schema")


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


def test_before_dataset_index_indexes_publisher_and_creator_identifier_and_country():
    plugin_instance = plugin.GdiUserPortalPlugin()
    input_data = {
        "publisher": [
            {
                "name": "Health-RI",
                "uri": "internalURI:publisher0",
                "email": "mailto:info@health-ri.nl",
                "url": "https://www.health-ri.nl",
                "type": "http://purl.org/adms/publishertype/NonProfitOrganisation",
                "identifier": "https://ror.org/05sk8w809",
                "country": "http://publications.europa.eu/resource/authority/country/NLD",
            }
        ],
        "creator": [
            {
                "name": "Dr. Jane Doe",
                "uri": "https://example.org/agents/jane-doe",
                "email": "mailto:jane.doe@example.org",
                "url": "https://example.org/jane-doe",
                "type": "http://xmlns.com/foaf/0.1/Person",
                "identifier": "https://orcid.org/0000-0002-9095-9201",
                "country": "http://publications.europa.eu/resource/authority/country/BEL",
            }
        ],
    }

    result = plugin_instance.before_dataset_index(input_data.copy())

    assert result["publisher_uri"] == ["internalURI:publisher0"]
    assert result["publisher_email"] == ["mailto:info@health-ri.nl"]
    assert result["publisher_url"] == ["https://www.health-ri.nl"]
    assert result["publisher_type"] == [
        "http://purl.org/adms/publishertype/NonProfitOrganisation"
    ]
    assert result["publisher_identifier"] == ["https://ror.org/05sk8w809"]
    assert result["publisher_country"] == [
        "http://publications.europa.eu/resource/authority/country/NLD"
    ]
    assert result["creator_uri"] == ["https://example.org/agents/jane-doe"]
    assert result["creator_email"] == ["mailto:jane.doe@example.org"]
    assert result["creator_url"] == ["https://example.org/jane-doe"]
    assert result["creator_type"] == ["http://xmlns.com/foaf/0.1/Person"]
    assert result["creator_identifier"] == ["https://orcid.org/0000-0002-9095-9201"]
    assert result["creator_country"] == [
        "http://publications.europa.eu/resource/authority/country/BEL"
    ]


def test_before_dataset_index_indexes_contact_point_fields():
    plugin_instance = plugin.GdiUserPortalPlugin()
    input_data = {
        "extras_contact": json.dumps(
            [
                {
                    "uri": "internalURI:contactPoint0",
                    "name": "Health-RI service desk",
                    "email": "mailto:servicedesk@health-ri.nl",
                    "identifier": "https://ror.org/05sk8w809",
                    "url": "https://www.health-ri.nl/contact",
                }
            ]
        )
    }

    result = plugin_instance.before_dataset_index(input_data.copy())

    assert result["contact_point_uri"] == ["internalURI:contactPoint0"]
    assert result["contact_point_name"] == ["Health-RI service desk"]
    assert result["contact_point_email"] == ["mailto:servicedesk@health-ri.nl"]
    assert result["contact_point_identifier"] == ["https://ror.org/05sk8w809"]
    assert result["contact_point_url"] == ["https://www.health-ri.nl/contact"]
    # contact is not repeating_once, so it must not collapse to a single flattened value
    assert "extras_contact" not in result


def test_before_dataset_index_flattens_json_encoded_contact_url_list():
    plugin_instance = plugin.GdiUserPortalPlugin()
    input_data = {
        "contact": [
            {
                "name": "Contact Point",
                "url": json.dumps(["https://www.example.com/website_contactPoint1"]),
            }
        ]
    }

    result = plugin_instance.before_dataset_index(input_data.copy())

    assert result["contact_point_url"] == ["https://www.example.com/website_contactPoint1"]


def test_before_dataset_index_indexes_multiple_contact_points():
    plugin_instance = plugin.GdiUserPortalPlugin()
    input_data = {
        "contact": [
            {"name": "General enquiries", "email": "mailto:info@example.org"},
            {"name": "Data access requests", "email": "mailto:dar@example.org"},
        ]
    }

    result = plugin_instance.before_dataset_index(input_data.copy())

    assert set(result["contact_point_name"]) == {
        "General enquiries",
        "Data access requests",
    }
    assert set(result["contact_point_email"]) == {
        "mailto:info@example.org",
        "mailto:dar@example.org",
    }


def test_before_dataset_index_indexes_qualified_relation_single_entry():
    plugin_instance = plugin.GdiUserPortalPlugin()
    input_data = {
        "qualified_relation": [
            {
                "uri": "https://example.org/relation/1",
                "relation": "https://example.org/related-resource/1",
                "role": "http://www.iana.org/assignments/relation/related",
            }
        ]
    }

    result = plugin_instance.before_dataset_index(input_data.copy())

    assert result["qualified_relation_uri"] == ["https://example.org/relation/1"]
    assert result["qualified_relation_relation"] == [
        "https://example.org/related-resource/1"
    ]
    assert result["qualified_relation_role"] == [
        "http://www.iana.org/assignments/relation/related"
    ]
    # text: false: scheming makes no extras_ text of the list
    assert "qualified_relation" not in result


def test_before_dataset_index_does_not_space_join_multiple_qualified_relation_entries():
    plugin_instance = plugin.GdiUserPortalPlugin()
    input_data = {
        "qualified_relation": [
            {
                "uri": "https://example.org/relation/1",
                "relation": "https://example.org/related-resource/1",
                "role": "http://www.iana.org/assignments/relation/related",
            },
            {
                "uri": "https://example.org/relation/2",
                "relation": "https://example.org/related-resource/2",
                "role": "http://www.iana.org/assignments/relation/references",
            },
        ]
    }

    result = plugin_instance.before_dataset_index(input_data.copy())

    assert sorted(result["qualified_relation_uri"]) == [
        "https://example.org/relation/1",
        "https://example.org/relation/2",
    ]
    assert sorted(result["qualified_relation_relation"]) == [
        "https://example.org/related-resource/1",
        "https://example.org/related-resource/2",
    ]
    assert sorted(result["qualified_relation_role"]) == [
        "http://www.iana.org/assignments/relation/references",
        "http://www.iana.org/assignments/relation/related",
    ]
    assert " " not in result["qualified_relation_uri"][0]


def test_before_dataset_index_indexes_quality_annotation_fields():
    plugin_instance = plugin.GdiUserPortalPlugin()
    input_data = {
        "quality_annotation": [
            {
                "body": "https://example.org/quality-certificate/1",
                "target": "https://example.org/dataset/test",
                "motivated_by": "http://www.w3.org/ns/oa#assessing",
            }
        ]
    }

    result = plugin_instance.before_dataset_index(input_data.copy())

    assert result["quality_annotation_body"] == [
        "https://example.org/quality-certificate/1"
    ]
    assert result["quality_annotation_target"] == ["https://example.org/dataset/test"]
    assert result["quality_annotation_motivated_by"] == [
        "http://www.w3.org/ns/oa#assessing"
    ]


def test_before_dataset_index_indexes_retention_period_fields():
    plugin_instance = plugin.GdiUserPortalPlugin()
    input_data = {
        "retention_period": [
            {"start": "2026-01-01T00:00:00Z", "end": "2030-01-01T00:00:00Z"}
        ]
    }

    result = plugin_instance.before_dataset_index(input_data.copy())

    assert result["retention_period_start"] == ["2026-01-01T00:00:00Z"]
    assert result["retention_period_end"] == ["2030-01-01T00:00:00Z"]


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


def _translations(rows):
    """``before_dataset_index`` with the translations the term_translation_show action would give."""
    show = MagicMock(return_value=rows)
    patched = patch(
        "ckanext.gdi_userportal.plugin.toolkit.get_action",
        side_effect=lambda action_name: show if action_name == "term_translation_show" else MagicMock(),
    )
    return show, patched


def _row(term, translation, lang="en"):
    return {"term": term, "term_translation": translation, "lang_code": lang}


def test_before_dataset_index_puts_the_labels_of_the_terms_in_the_free_text():
    plugin_instance = plugin.GdiUserPortalPlugin()
    input_data = {
        "extras_conforms_to": json.dumps(["http://example.org/spec"]),
        "extras_code_values": json.dumps(["http://www.wikidata.org/entity/Q12125"]),
        "extras_coding_system": json.dumps(["https://www.wikidata.org/entity/P494"]),
    }
    show, patched = _translations(
        [
            _row("http://example.org/spec", "Specification"),
            _row("http://example.org/spec", "Specificatie", "nl"),
            _row("http://www.wikidata.org/entity/Q12125", "Disease"),
            _row("https://www.wikidata.org/entity/P494", "ICD-10 identifier"),
        ]
    )

    with patched:
        result = plugin_instance.before_dataset_index(input_data.copy())

    show.assert_called_once()
    assert set(show.call_args.args[1]["terms"]) == {
        "http://example.org/spec",
        "http://www.wikidata.org/entity/Q12125",
        "https://www.wikidata.org/entity/P494",
    }
    assert set(result["text"]) == {
        "http://example.org/spec",
        "Specification",
        "Specificatie",
        "http://www.wikidata.org/entity/Q12125",
        "Disease",
        "https://www.wikidata.org/entity/P494",
        "ICD-10 identifier",
    }
    assert not any(key.startswith("vocab_") and key.endswith("_search") for key in result)
    assert not any(key.startswith("extras_") for key in result)  # the JSON text is not indexed


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

    assert "qualified_attribution" not in result  # the objects are not indexed, their values are
    assert {"Org A", "Org B", "Org C", "http://example.org/role/processor"} <= set(result["text"])
    assert result["vocab_qualified_attribution_role"] == [
        "http://example.org/role/processor",
        "http://example.org/role/controller",
    ]
    assert result["vocab_qualified_attribution_agent_name"] == [
        "Org A",
        "Org B",
        "Org C",
    ]


def test_before_dataset_index_keeps_raw_values_when_translations_are_missing():
    plugin_instance = plugin.GdiUserPortalPlugin()
    input_data = {"extras_code_values": json.dumps(["http://www.wikidata.org/entity/Q12125"])}
    _, patched = _translations([])

    with patched:
        result = plugin_instance.before_dataset_index(input_data.copy())

    assert result["text"] == ["http://www.wikidata.org/entity/Q12125"]


def test_before_dataset_index_deduplicates_terms_and_translations():
    plugin_instance = plugin.GdiUserPortalPlugin()
    input_data = {
        "extras_code_values": json.dumps(
            ["http://www.wikidata.org/entity/Q12125", "http://www.wikidata.org/entity/Q12125"]
        ),
    }
    _, patched = _translations(
        [
            _row("http://www.wikidata.org/entity/Q12125", "Disease"),
            _row("http://www.wikidata.org/entity/Q12125", "Disease", "nl"),
            _row(123, "Invalid"),  # non-string term, should be ignored
            _row("http://www.wikidata.org/entity/Q12125", ""),  # empty translation, should be ignored
            _row("http://www.wikidata.org/entity/Q12125", "   "),  # whitespace-only translation, should be ignored
        ]
    )

    with patched:
        result = plugin_instance.before_dataset_index(input_data.copy())

    assert result["text"] == ["http://www.wikidata.org/entity/Q12125", "Disease"]


def test_before_dataset_index_adds_the_labels_of_the_terms_in_the_distributions():
    plugin_instance = plugin.GdiUserPortalPlugin()
    # CKAN gives the extras of the distributions as one list per field, a JSON text per distribution
    input_data = {
        "extras_conforms_to": json.dumps(["http://example.org/spec"]),
        "res_extras_conforms_to": [json.dumps(["http://example.org/resource-spec"])],
        "res_extras_access_services": [json.dumps([{"conforms_to": ["http://example.org/access-service-spec"]}])],
    }
    _, patched = _translations(
        [
            _row("http://example.org/spec", "Specification"),
            _row("http://example.org/resource-spec", "Resource specification"),
            _row("http://example.org/access-service-spec", "Access service specification"),
        ]
    )

    with patched:
        result = plugin_instance.before_dataset_index(input_data.copy())

    assert {"Specification", "Resource specification", "Access service specification"} <= set(result["text"])


def test_before_dataset_index_handles_malformed_resource_access_services():
    plugin_instance = plugin.GdiUserPortalPlugin()
    input_data = {
        "extras_conforms_to": "http://example.org/spec",
        "res_extras_access_services": "not-json",
    }
    _, patched = _translations([_row("http://example.org/spec", "Specification")])

    with patched:
        result = plugin_instance.before_dataset_index(input_data.copy())

    assert result["conforms_to"] == "http://example.org/spec"
    assert {"http://example.org/spec", "Specification"} <= set(result["text"])


def test_before_dataset_index_is_not_stopped_by_translations_that_cannot_be_read():
    plugin_instance = plugin.GdiUserPortalPlugin()
    show = MagicMock(side_effect=RuntimeError("no database"))
    patched = patch(
        "ckanext.gdi_userportal.plugin.toolkit.get_action",
        side_effect=lambda action_name: show if action_name == "term_translation_show" else MagicMock(),
    )

    with patched:
        result = plugin_instance.before_dataset_index({"extras_code_values": json.dumps(["http://x.org/a"])})

    assert result["text"] == ["http://x.org/a"]


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


TAGS_FIELDS = [{"field_name": "tags_translated", "preset": "fluent_tags"}]


def _merge(document):
    return indexing.merge_translated_keywords_all(document, TAGS_FIELDS)


class TestMergeTagsTranslatedForIndexing:
    """The keywords of a multilingual keyword field (``fluent_tags``) are added to the field it translates."""

    def test_no_tags_translated_returns_unchanged(self):
        """When no tags_translated field exists, data is unchanged."""
        input_data = {"tags": ["existing-tag"], "title": "Test"}

        result = _merge(input_data.copy())

        assert result["tags"] == ["existing-tag"]
        assert result["title"] == "Test"

    def test_merges_tags_translated_into_tags(self):
        """Tags from tags_translated are merged into tags field."""
        input_data = {
            "tags": ["harvested-tag"],
            "extras_tags_translated": json.dumps({
                "en": ["manual-tag-en"],
                "nl": ["manual-tag-nl"]
            })
        }

        result = _merge(input_data.copy())

        assert "harvested-tag" in result["tags"]
        assert "manual-tag-en" in result["tags"]
        assert "manual-tag-nl" in result["tags"]

    def test_removes_duplicates(self):
        """Duplicate tags are not added twice."""
        input_data = {
            "tags": ["same-tag", "unique-tag"],
            "extras_tags_translated": json.dumps({
                "en": ["same-tag", "another-tag"]
            })
        }

        result = _merge(input_data.copy())

        assert result["tags"].count("same-tag") == 1
        assert "unique-tag" in result["tags"]
        assert "another-tag" in result["tags"]

    def test_handles_empty_tags_list(self):
        """Works when existing tags is empty list."""
        input_data = {
            "tags": [],
            "extras_tags_translated": json.dumps({
                "en": ["translated-only"]
            })
        }

        result = _merge(input_data.copy())

        assert result["tags"] == ["translated-only"]

    def test_handles_no_existing_tags(self):
        """Works when tags field doesn't exist."""
        input_data = {
            "extras_tags_translated": json.dumps({
                "en": ["new-tag"]
            })
        }

        result = _merge(input_data.copy())

        assert result["tags"] == ["new-tag"]

    def test_handles_invalid_json(self):
        """Invalid JSON in tags_translated returns unchanged."""
        input_data = {
            "tags": ["existing"],
            "extras_tags_translated": "not valid json"
        }

        result = _merge(input_data.copy())

        assert result["tags"] == ["existing"]

    def test_handles_non_dict_tags_translated(self):
        """Non-dict tags_translated returns unchanged."""
        input_data = {
            "tags": ["existing"],
            "extras_tags_translated": json.dumps(["not", "a", "dict"])
        }

        result = _merge(input_data.copy())

        assert result["tags"] == ["existing"]

    def test_filters_blank_tags(self):
        """Blank and whitespace-only tags are filtered out."""
        input_data = {
            "tags": ["valid"],
            "extras_tags_translated": json.dumps({
                "en": ["", "  ", "valid-translated"]
            })
        }

        result = _merge(input_data.copy())

        assert "" not in result["tags"]
        assert "  " not in result["tags"]
        assert "valid" in result["tags"]
        assert "valid-translated" in result["tags"]

    def test_trims_whitespace(self):
        """Whitespace around tags is trimmed."""
        input_data = {
            "tags": [],
            "extras_tags_translated": json.dumps({
                "en": ["  spaced tag  "]
            })
        }

        result = _merge(input_data.copy())

        assert "spaced tag" in result["tags"]
        assert "  spaced tag  " not in result["tags"]

    def test_handles_tags_as_string(self):
        """Works when existing tags is a string instead of list."""
        input_data = {
            "tags": "single-tag",
            "extras_tags_translated": json.dumps({
                "en": ["translated-tag"]
            })
        }

        result = _merge(input_data.copy())

        assert "single-tag" in result["tags"]

    def test_every_multilingual_keyword_field_of_the_schema_is_merged(self):
        """The fields come from the schema: a keyword field of another name merges into its own base field."""
        fields = [{"field_name": "keyword_translated", "preset": "fluent_tags"}]
        document = {"keyword": ["a"], "extras_keyword_translated": json.dumps({"en": ["b"]})}

        result = indexing.merge_translated_keywords_all(document, fields)

        assert result["keyword"] == ["a", "b"]

    def test_a_field_that_is_not_a_multilingual_keyword_field_is_left_alone(self):
        """No preset, or a name that is not ``<x>_translated``: nothing to merge into."""
        fields = [
            {"field_name": "tags_translated"},
            {"field_name": "tags", "preset": "fluent_tags"},
            {"field_name": "title_translated", "preset": "fluent_text"},
        ]
        document = {
            "tags": ["a"],
            "extras_tags_translated": json.dumps({"en": ["b"]}),
            "extras_title_translated": json.dumps({"en": ["c"]}),
        }

        assert indexing.merge_translated_keywords_all(dict(document), fields) == document

    def test_a_schema_that_cannot_be_read_leaves_the_document_alone(self):
        document = {"tags": ["a"], "extras_tags_translated": json.dumps({"en": ["b"]})}

        assert indexing.merge_translated_keywords_all(dict(document), []) == document


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

    def test_allows_equal_min_and_max(self):
        plugin_instance = plugin.GdiUserPortalPlugin()
        search_params = {
            "extras": {
                "ext_temporal_min": "2022-01-01",
                "ext_temporal_max": "2022-01-01",
            }
        }

        result = plugin_instance.before_dataset_search(search_params)

        assert result["fq_list"] == [
            "temporal_coverage_range:[2022-01-01T00:00:00Z TO 2022-01-01T00:00:00Z]"
        ]


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

    def test_skips_periods_with_invalid_dates(self):
        plugin_instance = plugin.GdiUserPortalPlugin()
        data_dict = {
            "temporal_coverage": [{"start": "not-a-date", "end": "also-bad"}]
        }

        result = plugin_instance._build_temporal_coverage_ranges(data_dict)

        assert "temporal_coverage_range" not in result
        assert "temporal_coverage_min" not in result
        assert "temporal_coverage_max" not in result

    def test_no_bounded_periods_results_in_no_range_fields(self):
        plugin_instance = plugin.GdiUserPortalPlugin()
        data_dict = {"temporal_coverage": [{}, "invalid"]}

        result = plugin_instance._build_temporal_coverage_ranges(data_dict)

        assert "temporal_coverage_range" not in result
        assert "temporal_coverage_min" not in result
        assert "temporal_coverage_max" not in result


def test_before_dataset_index_keeps_one_value_of_the_landing_page_and_type_for_solr(r8_indexing_schema):
    plugin_instance = plugin.GdiUserPortalPlugin()

    result = plugin_instance.before_dataset_index(
        {"url": ["http://example.org/p1", "http://example.org/p2"], "dcat_type": ["http://example.org/t1", "http://example.org/t2"]}
    )

    assert result["url"] == "http://example.org/p1"
    assert result["dcat_type"] == "http://example.org/t1"
    assert result["vocab_dcat_type"] == ["http://example.org/t1", "http://example.org/t2"]


def test_before_dataset_index_reads_a_json_landing_page_and_leaves_single_values_alone(r8_indexing_schema):
    plugin_instance = plugin.GdiUserPortalPlugin()

    result = plugin_instance.before_dataset_index({"url": '["http://example.org/p1"]', "dcat_type": "http://example.org/t1"})

    assert result["url"] == "http://example.org/p1"
    assert result["dcat_type"] == "http://example.org/t1"
    assert "vocab_dcat_type" not in result


def test_before_dataset_index_drops_an_empty_list_of_types(r8_indexing_schema):
    plugin_instance = plugin.GdiUserPortalPlugin()

    assert "dcat_type" not in plugin_instance.before_dataset_index({"dcat_type": []})


def test_before_dataset_index_indexes_the_relations_and_roles_of_a_relationship_that_hold_lists():
    plugin_instance = plugin.GdiUserPortalPlugin()

    result = plugin_instance.before_dataset_index(
        {
            "qualified_relation": [
                {"uri": "http://example.org/rel", "relation": ["http://example.org/a", "http://example.org/b"], "role": ["http://example.org/r1"]},
                {"uri": "", "relation": "http://example.org/b", "role": ["http://example.org/r2", "http://example.org/r1"]},
            ]
        }
    )

    assert result["qualified_relation_relation"] == ["http://example.org/a", "http://example.org/b"]
    assert result["qualified_relation_role"] == ["http://example.org/r1", "http://example.org/r2"]
    assert result["qualified_relation_uri"] == ["http://example.org/rel"]


def test_the_landing_page_and_type_are_flattened_after_the_extras_are_parsed_into_lists(r8_indexing_schema):
    plugin_instance = plugin.GdiUserPortalPlugin()

    result = plugin_instance.before_dataset_index(
        {"extras_dcat_type": json.dumps(["http://example.org/t1", "http://example.org/t2"])}
    )

    assert result["dcat_type"] == "http://example.org/t1"
    assert result["vocab_dcat_type"] == ["http://example.org/t1", "http://example.org/t2"]


def test_before_dataset_index_expands_lists_that_are_stored_as_json_inside_a_subfield():
    plugin_instance = plugin.GdiUserPortalPlugin()

    result = plugin_instance.before_dataset_index(
        {
            "qualified_relation": [{"uri": "u", "relation": '["http://example.org/a", "http://example.org/b"]', "role": '["http://example.org/r"]'}],
            "qualified_attribution": [{"agent": [{"name": "Agent"}], "role": '["http://example.org/at-a", "http://example.org/at-b"]'}],
        }
    )

    assert result["qualified_relation_relation"] == ["http://example.org/a", "http://example.org/b"]
    assert result["qualified_relation_role"] == ["http://example.org/r"]
    assert result["vocab_qualified_attribution_role"] == ["http://example.org/at-a", "http://example.org/at-b"]
