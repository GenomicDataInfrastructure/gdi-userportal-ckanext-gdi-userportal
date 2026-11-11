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
    get_preferred_language,
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


def test_replace_package_translates_the_country_and_types_of_a_qualified_attribution_agent():
    deu = "http://publications.europa.eu/resource/authority/country/DEU"
    fra = "http://publications.europa.eu/resource/authority/country/FRA"
    package = {
        "qualified_attribution": [
            {
                "role": "http://example.com/role",
                "agent": [
                    {
                        "name": "Agent",
                        "type": "http://example.com/agent-type",
                        "publisher_type": ["http://example.com/agent-publisher-type"],
                        "country": [deu, fra],
                    }
                ],
            }
        ]
    }
    translation_dict = {
        deu: "Germany",
        fra: "France",
        "http://example.com/agent-type": "Translated Agent Type",
        "http://example.com/agent-publisher-type": "Translated Publisher Type",
    }

    agent = replace_package(package, translation_dict, lang="en")[
        "qualified_attribution"
    ][0]["agent"][0]

    assert [country["display_name"] for country in agent["country"]] == ["Germany", "France"]
    assert agent["type"]["display_name"] == "Translated Agent Type"
    assert [t["display_name"] for t in agent["publisher_type"]] == ["Translated Publisher Type"]


def test_replace_package_gives_agents_without_identifier_an_empty_list():
    package = {
        "publisher": [{"name": "Publisher"}],
        "creator": [{"name": "Creator 1"}, {"name": "Creator 2", "identifier": None}],
        "hdab": [{"name": "HDAB", "identifier": ""}],
    }

    result = replace_package(package, {}, lang="en")

    assert [a["identifier"] for a in result["publisher"]] == [[]]
    assert [a["identifier"] for a in result["creator"]] == [[], []]
    assert [a["identifier"] for a in result["hdab"]] == [[]]


def test_replace_package_keeps_the_identifiers_of_an_agent_as_a_list():
    package = {
        "publisher": [{"name": "Publisher", "identifier": "https://ror.org/05wg1m734"}],
        "creator": [{"name": "Creator", "identifier": ["ORCID: abc-123", "ROR: abc-123"]}],
    }

    result = replace_package(package, {}, lang="en")

    assert result["publisher"][0]["identifier"] == ["https://ror.org/05wg1m734"]
    assert result["creator"][0]["identifier"] == ["ORCID: abc-123", "ROR: abc-123"]


def test_replace_package_gives_nested_agents_an_identifier_list():
    package = {
        "publisher": [{"name": "Publisher"}],
        "qualified_attribution": [{"role": "http://example.com/role", "agent": [{"name": "A"}]}],
        "was_generated_by": [
            {
                "label": "Activity",
                "wasAssociatedWith": [
                    {"name": "Associated", "actedOnBehalfOf": [{"name": "Principal"}]}
                ],
            }
        ],
        "resources": [
            {
                "access_services": [
                    {"title": "Service", "creator": [{"name": "C"}], "publisher": [{"name": "P"}]}
                ]
            }
        ],
    }

    result = replace_package(package, {}, lang="en")

    access_service = result["resources"][0]["access_services"][0]
    activity_agent = result["was_generated_by"][0]["wasAssociatedWith"][0]
    assert result["publisher"][0]["identifier"] == []
    assert result["qualified_attribution"][0]["agent"][0]["identifier"] == []
    assert activity_agent["identifier"] == []
    assert activity_agent["actedOnBehalfOf"][0]["identifier"] == []
    assert access_service["creator"][0]["identifier"] == []
    assert access_service["publisher"][0]["identifier"] == []


def test_replace_package_gives_an_agent_returned_as_a_dict_an_identifier_list():
    package = {
        "publisher": {"name": "Publisher"},
        "was_generated_by": {
            "wasAssociatedWith": {
                "name": "Associated",
                "identifier": "x",
                "actedOnBehalfOf": {"name": "Parent"},
            }
        },
    }

    result = replace_package(package, {}, lang="en")

    assert result["publisher"]["identifier"] == []
    assert result["was_generated_by"]["wasAssociatedWith"]["actedOnBehalfOf"]["identifier"] == []
    assert result["was_generated_by"]["wasAssociatedWith"]["identifier"] == ["x"]


def test_replace_package_does_not_add_agents_or_identifiers_to_a_package_without_them():
    result = replace_package({"title": "No agents"}, {}, lang="en")

    assert not result.get("publisher")
    assert not result.get("creator")
    assert not result.get("hdab")


def test_replace_package_keeps_every_country_and_place_of_an_agent():
    nld = "http://publications.europa.eu/resource/authority/country/NLD"
    ams = "http://publications.europa.eu/resource/authority/place/AMS"
    deu = "http://publications.europa.eu/resource/authority/country/DEU"
    ber = "http://publications.europa.eu/resource/authority/place/BER"
    package = {"publisher": [{"name": "Publisher", "country": [nld, ams, deu, ber]}]}
    translation_dict = {nld: "Netherlands", ams: "Amsterdam", deu: "Germany", ber: "Berlin"}

    result = replace_package(package, translation_dict, lang="en")

    assert [(c["name"], c["display_name"]) for c in result["publisher"][0]["country"]] == [
        (nld, "Netherlands"),
        (ams, "Amsterdam"),
        (deu, "Germany"),
        (ber, "Berlin"),
    ]


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


class TestTheSchemaDecidesWhatIsTranslated:
    """Which fields are shown as {name, display_name}, which hold agents and which hold a text per language comes
    from the marks of the dataset schema, so a schema that marks other fields changes the API without a code change."""

    @staticmethod
    def schema(dataset_fields, resource_fields=(), form_languages=("en", "nl")):
        return {
            "dataset_fields": list(dataset_fields),
            "resource_fields": list(resource_fields),
            "form_languages": list(form_languages),
        }

    @staticmethod
    def use(schema):
        return patch("ckanext.gdi_userportal.schema_access.dataset_schema", return_value=schema)

    def test_a_field_marked_translate_is_shown_with_its_label_and_an_unmarked_one_is_not(self):
        schema = self.schema([{"field_name": "colour", "translate": True}, {"field_name": "shape"}])
        package = {"colour": "red", "shape": "round"}

        with self.use(schema):
            terms = collect_values_to_translate(deepcopy(package))
            result = replace_package(package, {"red": "Rood", "round": "Rond"}, lang="en")

        assert terms == ["red"]
        assert result["colour"] == {"name": "red", "display_name": "Rood", "count": None}
        assert result["shape"] == "round"

    def test_the_label_is_written_to_the_sibling_a_mark_names(self):
        schema = self.schema(
            [
                {
                    "field_name": "activity",
                    "repeating_subfields": [{"field_name": "kind", "translate": {"label_in": "label"}}],
                }
            ]
        )
        package = {"activity": [{"kind": "http://x/kind", "label": "Raw"}]}

        with self.use(schema):
            result = replace_package(package, {"http://x/kind": "Kind"}, lang="en")

        assert result["activity"] == [{"kind": "http://x/kind", "label": "Kind"}]

    def test_only_the_fields_marked_agent_get_an_identifier_list(self):
        schema = self.schema(
            [
                {"field_name": "owner", "agent": True, "repeating_subfields": [{"field_name": "name"}]},
                {"field_name": "contact", "repeating_subfields": [{"field_name": "name"}]},
            ]
        )
        package = {"owner": [{"name": "O"}], "contact": [{"name": "C"}]}

        with self.use(schema):
            result = replace_package(package, {}, lang="en")

        assert result["owner"][0]["identifier"] == []
        assert "identifier" not in result["contact"][0]

    def test_a_multilingual_text_field_of_the_schema_shows_one_language(self):
        schema = self.schema([{"field_name": "story", "preset": "fluent_markdown"}])

        with self.use(schema):
            result = replace_package({"story": {"en": "English", "nl": "Nederlands"}}, {}, lang="nl")

        assert result["story"] == "Nederlands"

    def test_a_form_language_of_the_schema_is_a_language_of_the_api_too(self):
        with self.use(self.schema([], form_languages=("en", "nl", "de"))):
            assert get_preferred_language("de-DE") == "de"
            assert get_preferred_language("fr") == "en"

    def test_a_portal_with_an_english_form_still_answers_in_dutch(self):
        for schema in (self.schema([], form_languages=("en",)), {}):
            with self.use(schema):
                assert get_preferred_language("nl") == "nl"

    def test_the_core_type_of_a_dataset_is_translated_without_being_in_the_schema(self):
        with self.use(self.schema([])):
            result = replace_package({"type": "dataset"}, {"dataset": "Dataset"}, lang="en")

        assert result["type"] == {"name": "dataset", "display_name": "Dataset", "count": None}
