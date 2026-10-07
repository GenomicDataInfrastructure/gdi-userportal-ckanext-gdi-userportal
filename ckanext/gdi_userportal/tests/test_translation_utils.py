# SPDX-FileCopyrightText: 2025 Helath-RI
#
# SPDX-License-Identifier: Apache-2.0

from copy import deepcopy
from pathlib import Path
import sys

ROOT_DIR = Path(__file__).resolve().parents[3]
SRC_DIR = ROOT_DIR.parent

for path in (ROOT_DIR, SRC_DIR):
    path_str = str(path)
    if path_str not in sys.path:
        sys.path.append(path_str)

from unittest.mock import patch

import pytest

from ckanext.gdi_userportal.logic.action.translation_utils import (
    collect_values_to_translate,
    replace_package,
    replace_search_facets,
)


def _base_package():
    return {
        "title": "Original title",
        "title_translated": {"en": "English Title", "nl": "Nederlandse titel"},
        "notes": "Original notes",
        "notes_translated": {
            "en": "English Notes",
            "nl": "Nederlandse toelichting",
        },
        "provenance": {"en": "English provenance", "nl": "Nederlandse herkomst"},
        "population_coverage": {
            "en": "English coverage",
            "nl": "Nederlandse dekking",
        },
        "publisher_note": {
            "en": "English publisher note",
            "nl": "Nederlandse uitgeversnotitie",
        },
        "resources": [
            {
                "name": "Original resource name",
                "name_translated": {
                    "en": "English resource",
                    "nl": "Nederlandse resource",
                },
                "rights": {
                    "en": "English rights",
                    "nl": "Nederlandse rechten",
                },
            }
        ],
        "qualified_attribution": [
            {
                "role": "some-role",
                "agent": [
                    {
                        "name": "Original agent",
                        "name_translated": {
                            "en": "English agent",
                            "nl": "Nederlandse agent",
                        },
                    }
                ],
            }
        ],
        "qualified_relation": [
            {
                "relation": "http://example.com/related-dataset",
                "role": "http://www.iana.org/assignments/relation/related",
            }
        ],
        "quality_annotation": [
            {
                "body": "https://acertificateserver.eu/mycertificate",
                "target": "https://fair.healthdata.be/dataset/123",
            }
        ],
        "was_generated_by": [
            {
                "type": "http://example.com/activity-type",
                "dct_type": "http://example.com/dct-activity-type",
                "wasAssociatedWith": [
                    {
                        "type": "http://example.com/agent-type",
                        "actedOnBehalfOf": [
                            {
                                "type": "http://example.com/org-type",
                            }
                        ],
                    }
                ],
            },
            {
                "type": "",
                "dct_type": "",
                "wasAssociatedWith": [
                    {
                        "type": "",
                        "actedOnBehalfOf": [
                            {
                                "type": "",
                            }
                        ],
                    }
                ],
            }
        ],
    }


def test_replace_package_prefers_requested_language():
    package = deepcopy(_base_package())

    result = replace_package(package, translation_dict={}, lang="nl")

    assert result["title"] == "Nederlandse titel"
    assert result["notes"] == "Nederlandse toelichting"
    assert result["provenance"] == "Nederlandse herkomst"
    assert result["population_coverage"] == "Nederlandse dekking"
    assert result["publisher_note"] == "Nederlandse uitgeversnotitie"

    resource = result["resources"][0]
    assert resource["name"] == "Nederlandse resource"
    assert resource["rights"] == "Nederlandse rechten"

    attribution_agent = result["qualified_attribution"][0]["agent"][0]
    assert attribution_agent["name"] == "Nederlandse agent"

    was_generated_by = result["was_generated_by"][0]
    assert was_generated_by["type"] == {
        "name": "http://example.com/activity-type",
        "display_name": "http://example.com/activity-type",
        "count": None,
    }
    assert was_generated_by["dct_type"] == "http://example.com/dct-activity-type"
    assert was_generated_by["label"] == "http://example.com/dct-activity-type"
    associated_agent = was_generated_by["wasAssociatedWith"][0]
    assert associated_agent["type"] == {
        "name": "http://example.com/agent-type",
        "display_name": "http://example.com/agent-type",
        "count": None,
    }
    assert associated_agent["actedOnBehalfOf"][0]["type"] == {
        "name": "http://example.com/org-type",
        "display_name": "http://example.com/org-type",
        "count": None,
    }

    empty_was_generated_by = result["was_generated_by"][1]
    assert empty_was_generated_by["type"] == {
        "name": "",
        "display_name": "",
        "count": None,
    }
    assert empty_was_generated_by["dct_type"] == ""
    assert "label" not in empty_was_generated_by
    empty_associated_agent = empty_was_generated_by["wasAssociatedWith"][0]
    assert empty_associated_agent["type"] == {
        "name": "",
        "display_name": "",
        "count": None,
    }
    assert empty_associated_agent["actedOnBehalfOf"][0]["type"] == {
        "name": "",
        "display_name": "",
        "count": None,
    }

    qualified_relation_role = result["qualified_relation"][0]["role"]
    assert qualified_relation_role == {
        "name": "http://www.iana.org/assignments/relation/related",
        "display_name": "http://www.iana.org/assignments/relation/related",
        "count": None,
    }

    quality_annotation_body = result["quality_annotation"][0]["body"]
    assert quality_annotation_body == {
        "name": "https://acertificateserver.eu/mycertificate",
        "display_name": "https://acertificateserver.eu/mycertificate",
        "count": None,
    }


def test_replace_package_requested_language_empty_or_none():
    package = deepcopy(_base_package())

    # Set the requested language values to empty string and None
    package["title"] = {"en": "English title", "nl": ""}
    package["notes"] = {"en": "English notes", "nl": None}
    package["provenance"] = {"en": "English provenance", "nl": ""}
    package["population_coverage"] = {"en": "English coverage", "nl": None}
    package["publisher_note"] = {"en": "English publisher note", "nl": ""}

    package["resources"][0]["name"] = {"en": "English resource", "nl": ""}
    package["resources"][0]["rights"] = {"en": "English rights", "nl": None}

    package["qualified_attribution"][0]["agent"][0]["name"] = {"en": "English agent", "nl": ""}

    result = replace_package(package, translation_dict={}, lang="nl")

    # Should fallback to English when nl is empty or None
    assert result["title"] == "English title"
    assert result["notes"] == "English notes"
    assert result["provenance"] == "English provenance"
    assert result["population_coverage"] == "English coverage"
    assert result["publisher_note"] == "English publisher note"

    resource = result["resources"][0]
    assert resource["name"] == "English resource"
    assert resource["rights"] == "English rights"

    attribution_agent = result["qualified_attribution"][0]["agent"][0]
    assert attribution_agent["name"] == "English agent"

    qualified_relation_role = result["qualified_relation"][0]["role"]
    assert qualified_relation_role == {
        "name": "http://www.iana.org/assignments/relation/related",
        "display_name": "http://www.iana.org/assignments/relation/related",
        "count": None,
    }

    quality_annotation_body = result["quality_annotation"][0]["body"]
    assert quality_annotation_body == {
        "name": "https://acertificateserver.eu/mycertificate",
        "display_name": "https://acertificateserver.eu/mycertificate",
        "count": None,
    }


def test_replace_search_facets_translates_titles():
    facets = {
        "theme": {
            "title": "Theme",
            "items": [{"name": "health"}, {"name": "science"}],
        }
    }

    translation_dict = {"science": "Wetenschap"}

    with patch(
        "ckanext.gdi_userportal.logic.action.translation_utils.get_translations",
        return_value={"Theme": "Thema"},
    ) as mocked_get_translations:
        result = replace_search_facets(facets, translation_dict, lang="nl")

    mocked_get_translations.assert_called_once_with(["Theme"], lang="nl")
    theme_facet = result["theme"]
    assert theme_facet["title"] == "Thema"
    assert theme_facet["items"][0]["display_name"] == "health"
    assert theme_facet["items"][1]["display_name"] == "Wetenschap"


def test_replace_search_facets_falls_back_to_term_name():
    facets = {
        "format": {
            "title": "Format",
            "items": [{"name": "csv"}],
        }
    }

    translation_dict = {}

    with patch(
        "ckanext.gdi_userportal.logic.action.translation_utils.get_translations",
        return_value={},
    ):
        result = replace_search_facets(facets, translation_dict, lang="en")

    format_facet = result["format"]
    assert format_facet["title"] == "Format"
    assert format_facet["items"][0]["display_name"] == "csv"


def _display_names(result, facet):
    return [item["display_name"] for item in result[facet]["items"]]


def test_replace_search_facets_sorts_items_ascending_ignoring_case():
    # CKAN core hands the items over reversed and case-sensitive (z..aZ..A)
    facets = {
        "theme": {
            "title": "Theme",
            "items": [{"name": n} for n in ["z", "b", "C", "a", "B", "A", "c"]],
        }
    }

    with patch(
        "ckanext.gdi_userportal.logic.action.translation_utils.get_translations",
        return_value={},
    ):
        result = replace_search_facets(facets, {}, lang="en")

    assert _display_names(result, "theme") == ["A", "a", "B", "b", "C", "c", "z"]


def test_replace_search_facets_sorts_on_translated_label():
    facets = {
        "theme": {
            "title": "Theme",
            "items": [{"name": "science"}, {"name": "health"}, {"name": "land"}],
        }
    }
    translation_dict = {
        "science": "Wetenschap",
        "health": "Gezondheid",
        "land": "Landbouw",
    }

    with patch(
        "ckanext.gdi_userportal.logic.action.translation_utils.get_translations",
        return_value={"Theme": "Thema"},
    ):
        result = replace_search_facets(facets, translation_dict, lang="nl")

    # raw names would sort health, land, science; labels sort differently
    assert _display_names(result, "theme") == ["Gezondheid", "Landbouw", "Wetenschap"]


def test_replace_search_facets_sort_is_deterministic_for_equal_labels():
    translation_dict = {"x": "Same", "y": "same"}

    for names in (["x", "y"], ["y", "x"]):
        facets = {"theme": {"title": "Theme", "items": [{"name": n} for n in names]}}
        with patch(
            "ckanext.gdi_userportal.logic.action.translation_utils.get_translations",
            return_value={},
        ):
            result = replace_search_facets(facets, translation_dict, lang="en")

        assert [i["name"] for i in result["theme"]["items"]] == ["x", "y"]


def _facet_item_names(names, translation_dict):
    facets = {"theme": {"title": "Theme", "items": [{"name": n} for n in names]}}
    with patch(
        "ckanext.gdi_userportal.logic.action.translation_utils.get_translations",
        return_value={},
    ):
        result = replace_search_facets(facets, translation_dict, lang="en")

    return [i["name"] for i in result["theme"]["items"]]


def test_replace_search_facets_orders_identical_labels_by_name():
    translation_dict = {"x": "Same", "y": "Same", "z": "Same"}

    for names in (["x", "y", "z"], ["z", "y", "x"], ["y", "z", "x"]):
        assert _facet_item_names(names, translation_dict) == ["x", "y", "z"]


@pytest.mark.parametrize(
    "upper, lower",
    [("A", "a"), ("Ä", "ä"), ("Σ", "σ"), ("ẞ", "ß"), ("Ა", "ა")],
)
def test_replace_search_facets_puts_uppercase_first_in_any_alphabet(upper, lower):
    # ß/ẞ and the Georgian pair have the lowercase letter on the lower code point
    for names in ([lower, upper], [upper, lower]):
        assert _facet_item_names(names, {}) == [upper, lower]


def test_replace_search_facets_sorts_each_facet_and_keeps_counts():
    facets = {
        "theme": {
            "title": "Theme",
            "items": [{"name": "b", "count": 2}, {"name": "a", "count": 5}],
        },
        "format": {"title": "Format", "items": []},
    }

    with patch(
        "ckanext.gdi_userportal.logic.action.translation_utils.get_translations",
        return_value={},
    ):
        result = replace_search_facets(facets, {}, lang="en")

    assert [(i["name"], i["count"]) for i in result["theme"]["items"]] == [
        ("a", 5),
        ("b", 2),
    ]
    assert result["format"]["items"] == []


def test_replace_package_falls_back_to_default_language():
    package = deepcopy(_base_package())

    result = replace_package(package, translation_dict={}, lang="fr")

    assert result["title"] == "English Title"
    assert result["notes"] == "English Notes"
    assert result["provenance"] == "English provenance"
    assert result["population_coverage"] == "English coverage"
    assert result["publisher_note"] == "English publisher note"

    resource = result["resources"][0]
    assert resource["name"] == "English resource"
    assert resource["rights"] == "English rights"

    attribution_agent = result["qualified_attribution"][0]["agent"][0]
    assert attribution_agent["name"] == "English agent"

    qualified_relation_role = result["qualified_relation"][0]["role"]
    assert qualified_relation_role == {
        "name": "http://www.iana.org/assignments/relation/related",
        "display_name": "http://www.iana.org/assignments/relation/related",
        "count": None,
    }

    quality_annotation_body = result["quality_annotation"][0]["body"]
    assert quality_annotation_body == {
        "name": "https://acertificateserver.eu/mycertificate",
        "display_name": "https://acertificateserver.eu/mycertificate",
        "count": None,
    }


def test_replace_package_translates_nested_values():
    package = deepcopy(_base_package())

    translation_dict = {
        "http://www.iana.org/assignments/relation/related": "Related Resource",
        "https://acertificateserver.eu/mycertificate": "My Special Certificate",
        "http://example.com/activity-type": "Translated Activity Type",
        "http://example.com/dct-activity-type": "Test data",
        "http://example.com/agent-type": "Translated Agent Type",
        "http://example.com/org-type": "Translated Org Type",
    }

    result = replace_package(package, translation_dict, lang="en")

    qualified_relation_role = result["qualified_relation"][0]["role"]
    assert qualified_relation_role == {
        "name": "http://www.iana.org/assignments/relation/related",
        "display_name": "Related Resource",
        "count": None,
    }

    quality_annotation_body = result["quality_annotation"][0]["body"]
    assert quality_annotation_body == {
        "name": "https://acertificateserver.eu/mycertificate",
        "display_name": "My Special Certificate",
        "count": None,
    }

    was_generated_by = result["was_generated_by"][0]
    assert was_generated_by["type"]["display_name"] == "Translated Activity Type"
    assert was_generated_by["dct_type"] == "http://example.com/dct-activity-type"
    assert was_generated_by["label"] == "Test data"
    associated_agent = was_generated_by["wasAssociatedWith"][0]
    assert associated_agent["type"]["display_name"] == "Translated Agent Type"
    assert associated_agent["actedOnBehalfOf"][0]["type"]["display_name"] == "Translated Org Type"


def test_replace_package_normalizes_tags_to_strings():
    package = deepcopy(_base_package())
    package["tags"] = [
        {"name": "alpha", "display_name": "Alpha"},
        {"display_name": "Bravo"},
        "charlie",
    ]

    result = replace_package(package, translation_dict={}, lang="en")

    assert result["tags"] == ["alpha", "Bravo", "charlie"]


def test_collect_values_to_translate_includes_nested_fields():
    package = _base_package()

    values = collect_values_to_translate(package)

    assert "http://www.iana.org/assignments/relation/related" in values
    assert "https://acertificateserver.eu/mycertificate" in values
    assert "http://example.com/activity-type" in values
    assert "http://example.com/dct-activity-type" in values
    assert "http://example.com/agent-type" in values
    assert "http://example.com/org-type" in values
