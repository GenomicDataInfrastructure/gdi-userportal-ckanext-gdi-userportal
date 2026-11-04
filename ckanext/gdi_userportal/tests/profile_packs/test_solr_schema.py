# SPDX-FileCopyrightText: 2026 Stichting Health-RI
#
# SPDX-License-Identifier: Apache-2.0

"""
The Solr schema follows the generated dataset schema (profile_packs/solr_schema.py).

The drift tests fail when a dataset field of an enabled profile would be indexed into a Solr
field that rejects its values, so a pack change cannot ship a schema.xml that is out of date.
"""

import pytest
from conftest import PACKAGE_DIR, PACKS_DIR, load_module

SCHEMA_XML = PACKAGE_DIR.parents[1] / "solr" / "schema.xml"
PACKS = [["gdi_current"], ["healthdcat_r8"], ["gdi_current", "healthdcat_r8"], ["healthdcat_r8", "gdi_current"]]


@pytest.fixture(scope="module")
def solr():
    return load_module("profile_pack_solr_schema", PACKS_DIR / "solr_schema.py")


@pytest.fixture(scope="module")
def base(solr):
    return solr.parse_schema_xml(SCHEMA_XML)


def field(name, **attributes):
    return {"field_name": name, **attributes}


def spec(name, **attributes):
    return {"name": name, "type": "string", **attributes}


class Response:
    def __init__(self, body=b'{"responseHeader": {"status": 0}}'):
        self.body = body

    def read(self):
        return self.body

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


# -- drift: the generated schemas against solr/schema.xml -------------------------------------------


@pytest.mark.parametrize("packs", PACKS, ids="+".join)
def test_no_dataset_field_is_indexed_into_a_field_that_rejects_its_values(generator, solr, base, packs):
    fields = generator.build_schema(packs).schema["dataset_fields"]

    assert solr.check(base, fields) == []


@pytest.mark.parametrize("packs", PACKS, ids="+".join)
def test_every_dataset_field_has_a_solr_field_of_its_own(generator, solr, base, packs):
    fields = generator.build_schema(packs).schema["dataset_fields"]
    wanted = solr.wanted_schema(base, fields)

    for f in fields:
        name = f["field_name"]
        assert name in wanted.fields or solr.matching_dynamic_field(name, wanted.dynamic_fields), name


def test_the_flattened_fields_are_the_ones_the_plugin_flattens(solr):
    source = (PACKAGE_DIR / "plugin.py").read_text(encoding="utf-8")

    assert "_SINGLE_VALUED_SOLR_FIELDS = SINGLE_VALUED_SOLR_FIELDS" in source
    assert set(solr.SINGLE_VALUED_SOLR_FIELDS) == {"url", "dcat_type"}


def test_a_list_field_with_a_single_valued_solr_field_is_reported(solr):
    solr_base = solr.SolrSchema(fields={"theme": spec("theme", multiValued=False)}, field_types={"string"})
    problems = solr.check(solr_base, [field("theme", preset="multiple_text")])

    assert problems and "dataset_fields.theme" in problems[0]


def test_a_list_field_that_the_plugin_flattens_is_not_reported(solr):
    solr_base = solr.SolrSchema(fields={"url": spec("url")}, field_types={"string"})

    assert solr.check(solr_base, [field("url", preset="multiple_text")]) == []


# -- the fields that are derived ---------------------------------------------------------------------


@pytest.mark.parametrize("scheming_field, multivalued", [
    (field("a"), False),
    (field("a", preset="select"), False),
    (field("a", preset="multiple_text"), True),
    (field("a", preset="multiple_select"), True),
    (field("a", preset="dataset_series_in_series"), True),
    (field("a", validators="ignore_empty scheming_multiple_choice series_validator"), True),
    (field("a", validators="ignore_missing scheming_multiple_text"), True),
    (field("a", repeating_subfields=[field("b")]), True),
    (field("a", repeating_subfields=[field("b")], repeating_once=True), False),
])
def test_a_scheming_field_is_multi_valued_when_it_holds_a_list(solr, scheming_field, multivalued):
    assert solr.is_multivalued(scheming_field) is multivalued


def test_only_the_fields_that_schema_xml_does_not_declare_are_derived(solr):
    base = solr.SolrSchema(
        fields={"declared": spec("declared")},
        dynamic_fields={"vocab_*": spec("vocab_*"), "*": spec("*")},
        field_types={"string"},
    )
    fields = [field("declared"), field("vocab_thing"), field("own", preset="multiple_text"), field("plain")]

    assert solr.derive_fields(fields, base) == [
        {"name": "own", "type": "string", "indexed": True, "stored": False, "multiValued": True},
        {"name": "plain", "type": "string", "indexed": True, "stored": False, "multiValued": False},
    ]


def test_schema_xml_is_read_with_its_fields_dynamic_fields_and_copy_fields(solr, base):
    assert base.fields["publisher_country"]["multiValued"] is True
    assert base.fields["id"]["required"] is True
    assert base.dynamic_fields["*"]["type"] == "string"
    assert ("title", "title_ngram") in base.copy_fields
    assert {"string", "text", "date"} <= base.field_types


# -- the difference with a running core --------------------------------------------------------------


def live_schema(solr, **fields):
    return solr.SolrSchema(fields=fields, field_types={"string"})


def test_a_missing_field_is_added(solr):
    wanted = solr.SolrSchema(fields={"a": spec("a", multiValued=True)}, field_types={"string"})
    commands, problems = solr.plan(wanted, live_schema(solr))

    assert commands == [("add-field", spec("a", multiValued=True))] and problems == []


def test_a_field_that_differs_is_replaced(solr):
    wanted = solr.SolrSchema(fields={"a": spec("a", multiValued=True)}, field_types={"string"})
    commands, _ = solr.plan(wanted, live_schema(solr, a=spec("a")))

    assert commands == [("replace-field", spec("a", multiValued=True))]


def test_a_field_that_is_the_same_is_left_alone(solr):
    wanted = solr.SolrSchema(fields={"a": spec("a", multiValued=True, indexed=True)}, field_types={"string"})
    live = live_schema(solr, a={**spec("a", multiValued=True), "indexed": True, "stored": True})

    assert solr.plan(wanted, live)[0] == []


def test_the_defaults_of_solr_count_when_an_attribute_is_absent(solr):
    wanted = solr.SolrSchema(fields={"a": spec("a")}, field_types={"string"})

    assert solr.plan(wanted, live_schema(solr, a={**spec("a"), "multiValued": False, "stored": True}))[0] == []
    assert solr.plan(wanted, live_schema(solr, a={**spec("a"), "multiValued": True}))[0] != []


def test_a_field_that_only_the_core_has_is_never_removed(solr):
    wanted = solr.SolrSchema(field_types={"string"})

    assert solr.plan(wanted, live_schema(solr, old=spec("old")))[0] == []


def test_dynamic_fields_and_copy_fields_are_synced_too(solr):
    wanted = solr.SolrSchema(
        dynamic_fields={"vocab_*": spec("vocab_*", multiValued=True)},
        copy_fields=[("title", "title_ngram"), ("name", "text")],
        field_types={"string"},
    )
    live = solr.SolrSchema(dynamic_fields={"vocab_*": spec("vocab_*")}, copy_fields=[("name", "text")], field_types={"string"})
    commands, _ = solr.plan(wanted, live)

    assert commands == [
        ("replace-dynamic-field", spec("vocab_*", multiValued=True)),
        ("add-copy-field", {"source": "title", "dest": "title_ngram"}),
    ]


def test_a_field_type_the_core_lacks_is_a_problem_not_a_command(solr):
    wanted = solr.SolrSchema(fields={"a": {"name": "a", "type": "text_ngram"}}, field_types={"text_ngram"})
    commands, problems = solr.plan(wanted, live_schema(solr))

    assert commands == [] and "text_ngram" in problems[0]


def test_a_core_made_from_schema_xml_only_lacks_the_derived_fields(solr, base, generator):
    fields = generator.build_schema(["gdi_current", "healthdcat_r8"]).schema["dataset_fields"]
    wanted = solr.wanted_schema(base, fields)
    live = solr.SolrSchema(
        fields=dict(base.fields),
        dynamic_fields=dict(base.dynamic_fields),
        copy_fields=list(base.copy_fields),
        field_types=set(base.field_types),
    )
    commands, problems = solr.plan(wanted, live)

    assert problems == []
    assert {command for command, _ in commands} == {"add-field"}
    assert {s["name"] for _, s in commands} == {s["name"] for s in solr.derive_fields(fields, base)}


def test_the_core_is_changed_through_the_schema_api(solr, monkeypatch):
    sent = []
    monkeypatch.setattr(solr.urllib.request, "urlopen", lambda request, timeout=None: sent.append(request) or Response())
    solr.apply_commands("http://solr:8983/solr/ckan/", [("add-field", spec("a", multiValued=True))])

    assert sent[0].full_url == "http://solr:8983/solr/ckan/schema"
    assert sent[0].data == b'{"add-field": {"name": "a", "type": "string", "multiValued": true}}'


def test_a_schema_api_error_is_raised(solr, monkeypatch):
    monkeypatch.setattr(
        solr.urllib.request, "urlopen", lambda request, timeout=None: Response(b'{"errors": [{"errorMessages": ["nope"]}]}')
    )

    with pytest.raises(solr.SolrSchemaError, match="nope"):
        solr.apply_commands("http://solr", [("add-field", spec("a"))])
