# SPDX-FileCopyrightText: 2026 Stichting Health-RI
#
# SPDX-License-Identifier: Apache-2.0

"""
What the indexing writes for the ``solr`` key of a field (indexing.py).

The fields are made here, as small as the case needs. That the packs mark the fields the stack indexes is
checked by ``test_solr_schema.py`` and by ``test_characterization.py``, which indexes captured datasets.
"""

import json
import sys

import pytest
from conftest import PACKAGE_DIR

sys.path.insert(0, str(PACKAGE_DIR.parents[1]))

from ckanext.gdi_userportal import indexing  # noqa: E402


def field(name, *subfields, **attributes):
    return {"field_name": name, "repeating_subfields": [{"field_name": sub} for sub in subfields], **attributes}


def agent(name="publisher"):
    subfields = ("name", "uri", "email", "url", "type", "identifier", "country")
    return field(name, *subfields, solr={"flatten": list(subfields)})


def contact():
    subfields = ("uri", "name", "email", "identifier", "url")
    return field("contact", *subfields, solr={"prefix": "contact_point", "flatten": list(subfields)})


def relation():
    return field("qualified_relation", "uri", "relation", "role", solr={"flatten": ["uri", "relation", "role"]})


def attribution():
    return field(
        "qualified_attribution",
        "agent",
        "role",
        solr={"prefix": "vocab_qualified_attribution", "flatten": ["role", "agent.name"]},
    )


# -- agents ----------------------------------------------------------------------------------------


@pytest.mark.parametrize("name", ["publisher", "creator"])
def test_an_agent_has_its_identifier_and_country_indexed(name):
    document = {
        name: [
            {
                "name": "Health-RI",
                "identifier": "https://ror.org/05sk8w809",
                "country": "http://publications.europa.eu/resource/authority/country/NLD",
            }
        ]
    }

    result = indexing.flatten(document, agent(name))

    assert result[f"{name}_name"] == ["Health-RI"]
    assert result[f"{name}_identifier"] == ["https://ror.org/05sk8w809"]
    assert result[f"{name}_country"] == ["http://publications.europa.eu/resource/authority/country/NLD"]


def test_the_values_of_several_agents_are_indexed_once_each():
    document = {
        "creator": [
            {"name": "Org 1", "identifier": "same-id", "country": "same-country"},
            {"name": "Org 2", "identifier": "same-id", "country": "other-country"},
        ]
    }

    result = indexing.flatten(document, agent("creator"))

    assert result["creator_identifier"] == ["same-id"]
    assert result["creator_country"] == ["same-country", "other-country"]
    assert result["creator_name"] == ["Org 1", "Org 2"]


def test_an_agent_without_a_value_gets_no_field_for_it():
    result = indexing.flatten({"publisher": [{"name": "Org without extra fields"}]}, agent())

    assert result["publisher_name"] == ["Org without extra fields"]
    assert "publisher_identifier" not in result
    assert "publisher_country" not in result


def test_agents_given_as_json_text_are_read():
    document = {"creator": json.dumps([{"name": "Creator Org", "identifier": "creator-id"}])}

    assert indexing.flatten(document, agent("creator"))["creator_identifier"] == ["creator-id"]


def test_the_extras_stand_in_for_a_field_that_scheming_already_flattened():
    document = {
        "extras_publisher__name": "Health-RI",
        "extras_publisher__identifier": "https://ror.org/05sk8w809",
        "extras_publisher__country": json.dumps(["NLD", "DEU"]),
    }

    result = indexing.flatten(document, agent())

    assert result["publisher_name"] == ["Health-RI"]
    assert result["publisher_identifier"] == ["https://ror.org/05sk8w809"]
    assert result["publisher_country"] == ["NLD", "DEU"]


def test_the_extras_fallback_leaves_out_what_is_missing():
    result = indexing.flatten({"extras_creator__name": "Creator Org"}, agent("creator"))

    assert result["creator_name"] == ["Creator Org"]
    assert "creator_identifier" not in result


def test_the_space_joined_extras_of_several_entries_stay_one_value():
    # CKAN joins the subfield of every entry with a space: nothing can tell them apart afterwards
    assert indexing.flatten({"extras_creator__name": "Org 1 Org 2"}, agent("creator"))["creator_name"] == ["Org 1 Org 2"]


def test_nothing_to_flatten_changes_nothing():
    assert indexing.flatten({"unrelated": "value"}, agent()) == {"unrelated": "value"}


def test_the_values_a_subfield_holds_as_a_list_are_indexed_one_by_one():
    document = {"publisher": [{"name": "Org", "country": ["NLD", "DEU"], "identifier": ["id-1", "id-2"]}]}

    result = indexing.flatten(document, agent())

    assert result["publisher_country"] == ["NLD", "DEU"]
    assert result["publisher_identifier"] == ["id-1", "id-2"]


def test_empty_lists_add_no_field():
    result = indexing.flatten({"creator": [{"name": "Org", "country": [], "identifier": []}]}, agent("creator"))

    assert "creator_country" not in result
    assert "creator_identifier" not in result


# -- the contact point, named by solr.prefix --------------------------------------------------------


def test_the_contact_point_fields_start_with_the_prefix_of_the_field():
    document = {"contact": [{"uri": "internalURI:c0", "name": "Service desk", "email": "mailto:sd@example.org"}]}

    result = indexing.flatten(document, contact())

    assert result["contact_point_uri"] == ["internalURI:c0"]
    assert result["contact_point_name"] == ["Service desk"]
    assert result["contact_point_email"] == ["mailto:sd@example.org"]


def test_a_url_that_is_a_json_list_gives_one_value_per_url():
    document = {"contact": [{"name": "Contact Point", "url": json.dumps(["https://www.example.com/a", "https://www.example.com/b"])}]}

    assert indexing.flatten(document, contact())["contact_point_url"] == ["https://www.example.com/a", "https://www.example.com/b"]


def test_a_contact_point_given_as_its_name_only():
    assert indexing.flatten({"contact": "Health-RI service desk"}, contact())["contact_point_name"] == ["Health-RI service desk"]


def test_a_single_contact_point_object_is_one_entry():
    result = indexing.flatten({"contact": {"name": "Service desk", "email": "mailto:sd@health-ri.nl"}}, contact())

    assert result["contact_point_name"] == ["Service desk"]
    assert result["contact_point_email"] == ["mailto:sd@health-ri.nl"]


def test_the_contact_extras_stand_in_for_the_field():
    result = indexing.flatten({"extras_contact__name": "Service desk", "extras_contact__email": "mailto:sd@x.org"}, contact())

    assert result["contact_point_name"] == ["Service desk"]
    assert result["contact_point_email"] == ["mailto:sd@x.org"]


# -- the other repeating fields ---------------------------------------------------------------------


def test_a_relationship_gives_each_subfield_its_values_without_joining_them():
    document = {
        "qualified_relation": [
            {"uri": "https://example.org/relation/1", "relation": "https://example.org/r/1", "role": "related"},
            {"uri": "https://example.org/relation/2", "relation": "https://example.org/r/2", "role": "references"},
        ]
    }

    result = indexing.flatten(document, relation())

    assert result["qualified_relation_uri"] == ["https://example.org/relation/1", "https://example.org/relation/2"]
    assert result["qualified_relation_role"] == ["related", "references"]


def test_a_subfield_that_holds_a_list_inside_an_entry_is_expanded():
    document = {"qualified_relation": [{"relation": json.dumps(["a", "b"]), "role": ["x", "y"]}]}

    result = indexing.flatten(document, relation())

    assert result["qualified_relation_relation"] == ["a", "b"]
    assert result["qualified_relation_role"] == ["x", "y"]


def test_a_single_object_is_one_entry():
    result = indexing.flatten({"qualified_relation": {"uri": "https://example.org/relation/1"}}, relation())

    assert result["qualified_relation_uri"] == ["https://example.org/relation/1"]


@pytest.mark.parametrize("value", ["not valid json", 42])
def test_a_value_that_is_no_entry_changes_nothing(value):
    assert indexing.flatten({"qualified_relation": value}, relation()) == {"qualified_relation": value}


def test_a_field_without_a_flatten_key_is_left_alone():
    document = {"retention_period": [{"start": "2026-01-01"}]}

    assert indexing.flatten(document, field("retention_period", "start")) == {"retention_period": [{"start": "2026-01-01"}]}


def test_the_relation_extras_stand_in_for_the_field():
    result = indexing.flatten({"extras_qualified_relation__uri": "https://example.org/relation/1"}, relation())

    assert result["qualified_relation_uri"] == ["https://example.org/relation/1"]
    assert "qualified_relation_role" not in result


def test_a_repeating_field_marked_text_false_is_dropped_once_it_is_flattened():
    marked = field("retention_period", "start", "end", solr={"flatten": ["start", "end"], "text": False})

    result = indexing.flatten({"retention_period": [{"start": "2026-01-01", "end": None}]}, marked)

    assert result == {"retention_period_start": ["2026-01-01"]}


def test_flattened_values_are_stripped_and_empty_ones_dropped():
    result = indexing.flatten({"publisher": [{"name": "Org\n"}, {"name": "  "}, {"name": "Org"}]}, agent())

    assert result["publisher_name"] == ["Org"]


# -- a path into a subfield that has subfields ------------------------------------------------------


def test_the_roles_and_agent_names_of_an_attribution_are_indexed():
    document = {
        "qualified_attribution": [
            {"role": "http://example.org/role/processor", "agent": [{"name": "Org A"}, {"name": "Org B"}]},
            {"role": "http://example.org/role/controller", "agent": {"name": "Org C"}},
        ]
    }

    result = indexing.flatten(document, attribution())

    assert result["vocab_qualified_attribution_role"] == ["http://example.org/role/processor", "http://example.org/role/controller"]
    assert result["vocab_qualified_attribution_agent_name"] == ["Org A", "Org B", "Org C"]


@pytest.mark.parametrize(
    "agents, expected",
    [
        (None, []),
        (42, []),
        ("plain-org", ["plain-org"]),
        ('{"name": ["Org D", {"nested": "Org E"}]}', ["Org D", "Org E"]),
    ],
)
def test_the_agent_of_an_attribution_may_be_given_in_other_shapes(agents, expected):
    result = indexing.flatten({"qualified_attribution": [{"role": "r", "agent": agents}]}, attribution())

    assert result.get("vocab_qualified_attribution_agent_name", []) == expected


def test_an_agent_name_that_is_a_nested_object_gives_all_its_strings():
    document = {"qualified_attribution": [{"role": "r", "agent": {"name": {"primary": "Org B", "aliases": ["Org C"]}}}]}

    assert indexing.flatten(document, attribution())["vocab_qualified_attribution_agent_name"] == ["Org B", "Org C"]


@pytest.mark.parametrize("value", [123, ["skip me"]])
def test_attributions_that_are_no_objects_give_nothing(value):
    assert indexing.flatten({"qualified_attribution": value}, attribution()) == {"qualified_attribution": value}


# -- list fields and the extras copy ------------------------------------------------------------------


def multiple(name, **attributes):
    return {"field_name": name, "preset": "multiple_text", **attributes}


def test_the_json_text_of_a_list_field_becomes_a_list():
    document = {"theme": '["a", "b"]', "extras_theme": '["a", "b"]'}

    assert indexing.normalise(document, multiple("theme"))["theme"] == ["a", "b"]


def test_a_list_field_that_only_has_its_extras_copy_gets_its_value_from_there():
    assert indexing.normalise({"extras_theme": '["a"]'}, multiple("theme"))["theme"] == ["a"]


def test_decode_false_leaves_the_json_text_for_a_plugin_that_reads_it():
    # ckanext-dataset-series runs after this plugin and does json.loads(in_series)
    document = {"in_series": '["id1"]'}

    assert indexing.normalise(document, multiple("in_series", solr={"decode": False}))["in_series"] == '["id1"]'


def test_a_value_that_is_no_list_stays_as_it_is():
    assert indexing.normalise({"theme": "internalURI:x"}, multiple("theme"))["theme"] == "internalURI:x"


def test_the_extras_copy_stays_unless_the_field_says_text_false():
    kept = indexing.normalise({"theme": '["a"]', "extras_theme": '["a"]'}, multiple("theme"))
    dropped = indexing.normalise({"theme": '["a"]', "extras_theme": '["a"]'}, multiple("theme", solr={"text": False}))

    assert "extras_theme" in kept
    assert "extras_theme" not in dropped


def test_text_false_drops_the_extras_copy_of_a_single_value_too():
    result = indexing.normalise({"access_rights": "PUBLIC", "extras_access_rights": "PUBLIC"}, {"field_name": "access_rights", "solr": {"text": False}})

    assert result == {"access_rights": "PUBLIC"}


def test_a_field_that_holds_no_list_is_left_alone():
    document = {"frequency": '["not a list field"]', "extras_frequency": "x"}

    assert indexing.normalise(dict(document), {"field_name": "frequency"}) == document


def test_a_repeating_field_that_only_has_its_extras_copy_gets_its_value_from_there():
    result = indexing.normalise({"extras_contact": json.dumps([{"name": "Desk"}])}, field("contact", "name"))

    assert result == {"contact": [{"name": "Desk"}]}


# -- one value of a list --------------------------------------------------------------------------


def single(**solr):
    return multiple("dcat_type", solr={"multiple": False, **solr})


def test_the_first_value_is_kept_and_all_of_them_go_to_the_second_field():
    document = {"dcat_type": ["a", "b", "a"]}

    result = indexing.keep_one_value(document, single(all_values="vocab_dcat_type"))

    assert result["dcat_type"] == "a"
    assert result["vocab_dcat_type"] == ["a", "b"]


def test_a_json_list_is_read_and_a_single_value_is_left_alone():
    assert indexing.keep_one_value({"dcat_type": '["a", "b"]'}, single())["dcat_type"] == "a"
    assert indexing.keep_one_value({"dcat_type": "a"}, single()) == {"dcat_type": "a"}


def test_an_empty_list_leaves_no_value():
    assert indexing.keep_one_value({"dcat_type": []}, single(all_values="vocab_dcat_type")) == {}


def test_a_field_that_is_not_marked_single_valued_keeps_its_list():
    assert indexing.keep_one_value({"dcat_type": ["a", "b"]}, multiple("dcat_type")) == {"dcat_type": ["a", "b"]}


# -- the whole schema ------------------------------------------------------------------------------


def test_every_field_of_the_schema_is_looked_at_and_nameless_ones_are_skipped():
    fields = [agent(), {"label": "no name"}, multiple("theme")]

    document = indexing.normalise_all({"theme": '["a"]'}, fields)
    document = indexing.flatten_all({**document, "publisher": [{"name": "Org"}]}, fields)

    assert document["theme"] == ["a"]
    assert document["publisher_name"] == ["Org"]
    assert indexing.keep_one_value_all(document, fields) == document


# -- free text -------------------------------------------------------------------------------------

UTRECHT = "http://publications.europa.eu/resource/authority/place/NLD_UTC"


def labels(terms):
    known = {UTRECHT: ["Utrecht", "Utrecht (stad)"]}
    return {term: known[term] for term in terms if term in known}


def test_the_label_of_a_uri_in_a_property_is_searchable():
    document = {"spatial_coverage": [{"uri": UTRECHT, "text": ""}], "title": "x"}

    indexing.free_text_all(document, [field("spatial_coverage", "uri", "text")], translate=labels)

    assert document["text"] == [UTRECHT, "Utrecht", "Utrecht (stad)"]


def test_every_language_and_subfield_is_searchable_and_the_json_is_not_indexed():
    document = {
        "title_translated": {"en": "Heart", "nl": "Hart"},
        "extras_title_translated": '{"en": "Heart", "nl": "Hart"}',
        "contact": [{"name": "Health-RI", "email": "a@b.nl"}],
        "extras_contact__name": "Health-RI",
    }
    fields = [{"field_name": "title_translated", "preset": "fluent_text"}, field("contact", "name", "email")]

    indexing.free_text_all(document, fields)

    assert set(document["text"]) == {"Heart", "Hart", "Health-RI", "a@b.nl"}
    assert "title_translated" not in document and "extras_title_translated" not in document
    assert "contact" not in document and "extras_contact__name" not in document


def test_a_json_text_is_read_at_every_depth():
    document = {"access": json.dumps([{"note": json.dumps({"en": "Open", "nl": "Open data"})}])}

    indexing.free_text_all(document, [field("access", "note")])

    assert set(document["text"]) == {"Open", "Open data"}


def test_text_false_keeps_a_field_out_of_the_free_text():
    document = {"in_series": '["uuid-1"]', "theme": ["http://x.org/t"]}
    fields = [multiple("in_series", solr={"decode": False, "text": False}), multiple("theme")]

    indexing.free_text_all(document, fields)

    assert document["text"] == ["http://x.org/t"]
    assert document["in_series"] == '["uuid-1"]'


def test_a_plain_list_stays_under_its_own_name_for_the_filters():
    document = {"theme": ["http://x.org/t"], "extras_theme": '["http://x.org/t"]'}

    indexing.free_text_all(document, [multiple("theme")])

    assert document["theme"] == ["http://x.org/t"] and "extras_theme" not in document


def test_the_labels_of_the_terms_in_the_distributions_are_added():
    document = {"res_extras_spatial": ['["%s"]' % UTRECHT, "[]"]}

    indexing.free_text_all(document, [], translate=labels)

    assert document["text"] == ["Utrecht", "Utrecht (stad)"]  # the values themselves are copied by Solr


def test_a_distribution_field_marked_text_false_has_no_labels():
    document = {"res_extras_spatial": ['["%s"]' % UTRECHT]}

    indexing.free_text_all(document, [], translate=labels, resource_fields=[{"field_name": "spatial", "solr": {"text": False}}])

    assert "text" not in document


def test_only_a_term_is_looked_up_not_a_sentence():
    asked = []

    def translate(terms):
        asked.extend(terms)
        return {}

    document = {"notes": "A long description with spaces", "theme": ["http://x.org/t"], "code": "C0009"}
    indexing.free_text_all(document, [{"field_name": "notes"}, multiple("theme"), {"field_name": "code"}], translate=translate)

    assert set(asked) == {"http://x.org/t", "C0009"}


def test_what_is_in_the_free_text_already_stays():
    document = {"text": "already", "theme": ["a"]}

    indexing.free_text_all(document, [multiple("theme")])

    assert document["text"] == ["already", "a"]


def test_a_dataset_without_text_gets_no_free_text_field():
    document = {"issued": None}

    indexing.free_text_all(document, [{"field_name": "issued"}], translate=labels)

    assert "text" not in document


DATA_THEME = "http://publications.europa.eu/resource/authority/data-theme/"
THEME = {"field_name": "theme", "solr": {"canonical_prefix": DATA_THEME}}


class TestCanonicalUris:
    """``solr: {canonical_prefix}``: one form of the URI, so that one term is one filter value."""

    def test_the_other_scheme_of_the_prefix_is_rewritten_and_doubles_go(self):
        document = {"theme": [DATA_THEME.replace("http:", "https:") + "HEAL", DATA_THEME + "HEAL", DATA_THEME + "ENER"]}

        indexing.canonicalise_uris(document, THEME)

        assert document["theme"] == [DATA_THEME + "HEAL", DATA_THEME + "ENER"]

    def test_other_uris_stay_as_they_are(self):
        document = {"theme": ["https://example.org/theme/custom", DATA_THEME + "HEAL"]}

        indexing.canonicalise_uris(document, THEME)

        assert document["theme"] == ["https://example.org/theme/custom", DATA_THEME + "HEAL"]

    def test_a_single_value_is_rewritten_too(self):
        document = {"theme": DATA_THEME.replace("http:", "https:") + "HEAL"}

        indexing.canonicalise_uris(document, THEME)

        assert document["theme"] == DATA_THEME + "HEAL"

    @pytest.mark.parametrize("document", [{}, {"theme": None}])
    def test_a_field_without_a_value_is_left_alone(self, document):
        assert indexing.canonicalise_uris(dict(document), THEME) == document

    def test_a_field_without_the_mark_is_left_alone(self):
        document = {"theme": [DATA_THEME.replace("http:", "https:") + "HEAL"]}

        assert indexing.canonicalise_uris(dict(document), {"field_name": "theme"}) == document

    @pytest.mark.parametrize("prefix", ["urn:x:", "", None, 5])
    def test_a_prefix_without_a_scheme_to_swap_changes_nothing(self, prefix):
        document = {"theme": ["urn:x:a", "https://example.org/a"]}

        field = {"field_name": "theme", "solr": {"canonical_prefix": prefix}}

        assert indexing.canonicalise_uris(dict(document), field) == document

    def test_the_prefix_can_be_the_https_form(self):
        field = {"field_name": "x", "solr": {"canonical_prefix": "https://example.org/v/"}}
        document = {"x": ["http://example.org/v/a", "https://example.org/v/a"]}

        indexing.canonicalise_uris(document, field)

        assert document["x"] == ["https://example.org/v/a"]

    def test_values_that_are_not_texts_are_kept(self):
        document = {"theme": [{"name": "x"}, DATA_THEME + "HEAL", DATA_THEME + "HEAL"]}

        indexing.canonicalise_uris(document, THEME)

        assert document["theme"] == [{"name": "x"}, DATA_THEME + "HEAL"]
