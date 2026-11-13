# SPDX-FileCopyrightText: 2026 Stichting Health-RI
#
# SPDX-License-Identifier: Apache-2.0

"""
The Solr schema follows the generated dataset schema (profile_packs/solr_schema.py).

The drift tests fail when a dataset field of an enabled profile would be indexed into a Solr
field that rejects its values, so a pack change cannot ship a schema.xml that is out of date.
"""

import sys

import pytest
from conftest import PACKAGE_DIR

# solr_schema imports schema_fields by package, as it does when the start scripts run it with -m
sys.path.insert(0, str(PACKAGE_DIR.parents[1]))

from ckanext.gdi_userportal.profile_packs import solr_schema  # noqa: E402
from ckanext.gdi_userportal.profile_packs.schema_fields import FLUENT_TEXT_PRESETS, flattened_solr_fields, is_multiple  # noqa: E402

SCHEMA_XML = PACKAGE_DIR.parents[1] / "solr" / "schema.xml"
PACKS = [["gdi_current"], ["healthdcat_r8"], ["gdi_current", "healthdcat_r8"], ["healthdcat_r8", "gdi_current"]]


@pytest.fixture(scope="module")
def solr():
    return solr_schema


@pytest.fixture(scope="module")
def base(solr):
    return solr.parse_schema_xml(SCHEMA_XML)


def field(name, *subfields, **attributes):
    """A scheming field; the names after it are its repeating subfields."""
    made = {"field_name": name, **attributes}
    if subfields:
        made["repeating_subfields"] = [{"field_name": sub} for sub in subfields]
    return made


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
        if f.get("repeating_subfields") or f.get("preset") in FLUENT_TEXT_PRESETS:
            continue  # objects: the indexing writes their values, see the test below
        assert name in wanted.fields or solr.matching_dynamic_field(name, wanted.dynamic_fields), name


@pytest.mark.parametrize("packs", PACKS, ids="+".join)
def test_a_repeating_field_has_no_solr_field_of_its_own_but_the_fields_it_is_flattened_into(generator, solr, base, packs):
    fields = generator.build_schema(packs).schema["dataset_fields"]
    wanted = solr.wanted_schema(base, fields)

    for f in fields:
        if f.get("repeating_subfields") or f.get("preset") in FLUENT_TEXT_PRESETS:
            assert f["field_name"] not in wanted.fields, f["field_name"]
    assert "publisher_name" in wanted.fields


@pytest.mark.parametrize("packs", PACKS, ids="+".join)
def test_the_dataset_fields_are_made_from_the_dataset_schema_not_declared_in_schema_xml(generator, solr, base, packs):
    fields = generator.build_schema(packs).schema["dataset_fields"]

    assert [p for p in solr.check(base, fields) if "is declared in solr/schema.xml" in p] == []


@pytest.mark.parametrize("packs", PACKS, ids="+".join)
def test_the_numbers_and_dates_of_a_dataset_have_a_type_that_sorts_and_filters(generator, solr, base, packs):
    fields = generator.build_schema(packs).schema["dataset_fields"]
    wanted = solr.wanted_schema(base, fields)

    for name in ("min_typical_age", "max_typical_age", "number_of_records", "number_of_unique_individuals"):
        assert wanted.fields[name]["type"] == "long" and wanted.fields[name]["docValues"] is True, name
    for name in ("issued", "modified"):
        assert wanted.fields[name]["type"] == "date" and wanted.fields[name]["docValues"] is True, name
    assert wanted.fields["min_typical_age"]["stored"] is True


def test_a_field_declared_in_schema_xml_and_made_from_the_dataset_schema_is_reported(solr, base):
    declared = solr.SolrSchema(fields={**base.fields, "theme": spec("theme", multiValued=True)}, field_types=base.field_types)

    problems = solr.check(declared, [field("theme", preset="multiple_text")])

    assert any("theme is declared in solr/schema.xml" in problem for problem in problems)


def test_a_field_that_ckan_indexes_itself_may_be_declared_in_schema_xml_and_in_the_dataset_schema(solr, base):
    assert solr.check(base, [field("version"), field("license_id"), field("url")]) == []


AGENT = ["name", "uri", "email", "url", "type", "identifier", "country"]
# The subfields each profile indexes under the field name, as the solr keys of the fields say.
FLATTENED = {
    "gdi_current": {
        *("publisher_" + sub for sub in AGENT),
        *("creator_" + sub for sub in AGENT),
        *("contact_point_" + sub for sub in ("uri", "name", "email", "identifier", "url")),
        "qualified_relation_uri", "qualified_relation_relation", "qualified_relation_role",
        "quality_annotation_body", "quality_annotation_target", "quality_annotation_motivated_by",
        "retention_period_start", "retention_period_end",
        "spatial_coverage_uri",
        "vocab_qualified_attribution_role", "vocab_qualified_attribution_agent_name",
    },
    "healthdcat_r8": {
        *("publisher_" + sub for sub in ("name", "uri", "email", "url", "type")),
        *("creator_" + sub for sub in ("name", "uri", "type")),
        *("contact_point_" + sub for sub in ("uri", "email", "url")),
        "qualified_relation_uri", "qualified_relation_relation", "qualified_relation_role",
        "quality_annotation_body", "quality_annotation_target", "quality_annotation_motivated_by",
        "retention_period_start", "retention_period_end",
        "spatial_coverage_uri",
        "vocab_qualified_attribution_role", "vocab_qualified_attribution_agent_name",
    },
}


@pytest.mark.parametrize("pack", ["gdi_current", "healthdcat_r8"])
def test_a_pack_marks_the_fields_the_plugin_used_to_flatten_by_name(generator, pack):
    fields = generator.build_schema([pack]).schema["dataset_fields"]

    assert set(flattened_solr_fields(fields)) == FLATTENED[pack]


@pytest.mark.parametrize("packs", PACKS, ids="+".join)
def test_every_field_the_indexing_fills_is_multi_valued(generator, solr, base, packs):
    fields = generator.build_schema(packs).schema["dataset_fields"]
    wanted = solr.wanted_schema(base, fields)

    names = flattened_solr_fields(fields)
    assert names
    for name in names:
        spec = wanted.fields.get(name) or wanted.dynamic_fields.get(solr.matching_dynamic_field(name, wanted.dynamic_fields))
        assert spec and spec.get("multiValued") is True, name


@pytest.mark.parametrize("packs", PACKS, ids="+".join)
def test_a_flattened_subfield_is_one_the_field_has(generator, solr, base, packs):
    # check() reports a flatten key that names a subfield the field lacks
    assert not [p for p in solr.check(base, generator.build_schema(packs).schema["dataset_fields"]) if "flattens" in p]


def test_a_flattened_field_that_schema_xml_lacks_is_derived_multi_valued(solr, base):
    without = solr.SolrSchema(
        fields={k: v for k, v in base.fields.items() if k != "publisher_country"}, field_types=set(base.field_types)
    )
    publisher = field("publisher", "country", solr={"flatten": ["country"]})

    derived = {spec["name"]: spec for spec in solr.derive_fields([publisher], without)}

    assert derived["publisher_country"]["multiValued"] is True
    assert derived["publisher_country"]["type"] == "string"


def test_a_flattened_field_that_schema_xml_declares_single_valued_is_reported(solr, base):
    single = solr.SolrSchema(
        fields={**base.fields, "publisher_country": spec("publisher_country", multiValued=False)},
        field_types=set(base.field_types),
    )
    publisher = field("publisher", "country", solr={"flatten": ["country"]})

    assert any("publisher_country" in problem and "single valued" in problem for problem in solr.check(single, [publisher]))


def test_a_flatten_key_that_names_a_missing_subfield_is_reported(solr, base):
    publisher = field("publisher", "name", solr={"flatten": ["name", "nme"]})

    problems = solr.check(base, [publisher])

    assert any("dataset_fields.publisher" in p and "'nme'" in p for p in problems)


def test_a_dotted_flatten_path_reaches_into_a_subfield_with_subfields(solr, base):
    attribution = field("qualified_attribution", "role", solr={"flatten": ["agent.name"]})
    attribution["repeating_subfields"].append(field("agent", "name"))

    assert solr.check(base, [attribution]) == []
    assert any("agent.nme" in p for p in solr.check(base, [{**attribution, "solr": {"flatten": ["agent.nme"]}}]))


def test_a_list_field_with_a_single_valued_solr_field_is_reported(solr, base):
    solr_base = solr.SolrSchema(fields={**base.fields, "theme": spec("theme", multiValued=False)}, field_types=base.field_types)
    problems = solr.check(solr_base, [field("theme", preset="multiple_text")])

    assert any("dataset_fields.theme" in problem and "single valued" in problem for problem in problems)


def test_a_list_field_whose_solr_field_holds_one_value_is_not_reported(solr, base):
    solr_base = solr.SolrSchema(fields={**base.fields, "url": spec("url")}, field_types=base.field_types)

    assert solr.check(solr_base, [field("url", preset="multiple_text", solr={"multiple": False})]) == []


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
def test_a_scheming_field_is_multi_valued_when_it_holds_a_list(scheming_field, multivalued):
    assert is_multiple(scheming_field) is multivalued


def test_only_the_fields_that_schema_xml_does_not_declare_are_derived(solr):
    base = solr.SolrSchema(
        fields={"declared": spec("declared")},
        dynamic_fields={"vocab_*": spec("vocab_*"), "*": spec("*")},
        field_types={"string"},
    )
    fields = [field("declared"), field("vocab_thing"), field("own", preset="multiple_text"), field("plain")]

    assert solr.derive_fields(fields, base) == [
        {"name": "own", "type": "string", "indexed": True, "stored": True, "multiValued": True},
        {"name": "plain", "type": "string", "indexed": True, "stored": True, "multiValued": False},
    ]


@pytest.mark.parametrize("scheming_field, solr_type", [
    (field("a"), "string"),
    (field("a", preset="select", validators="ignore_missing scheming_choices"), "string"),
    (field("a", validators="ignore_missing int_validator"), "long"),
    (field("a", validators="ignore_missing boolean_validator"), "boolean"),
    (field("a", preset="datetime_flex"), "string"),  # a partial date is not a Solr date: opt in with solr: type
    (field("a", preset="fluent_markdown"), "string"),
])
def test_the_type_follows_from_the_validators(solr, scheming_field, solr_type):
    assert solr.solr_settings(scheming_field)["type"] == solr_type


def test_a_solr_key_on_the_field_overrides_what_follows_from_it(solr):
    settings = solr.solr_settings(
        field("a", preset="datetime_flex", solr={"type": "date", "index": False, "store": False, "multiple": True})
    )

    assert settings == {"name": "a", "type": "date", "indexed": False, "stored": False, "multiValued": True, "docValues": True}


def test_a_solr_key_with_part_of_the_settings_keeps_the_rest(solr):
    settings = solr.solr_settings(field("a", validators="int_validator", solr={"store": False}))

    assert settings == {"name": "a", "type": "long", "indexed": True, "stored": False, "multiValued": False, "docValues": True}


def test_a_field_is_stored_and_a_string_has_no_doc_values_unless_it_says_so(solr):
    assert solr.solr_settings(field("a")) == {"name": "a", "type": "string", "indexed": True, "stored": True, "multiValued": False}


def test_a_field_of_objects_gets_no_solr_field(solr):
    base = solr.SolrSchema(dynamic_fields={"*": spec("*")}, field_types={"string"})
    fields = [field("contact", "name"), field("title_translated", preset="fluent_text"), field("plain")]

    assert solr.derive_fields(fields, base) == [
        {"name": "plain", "type": "string", "indexed": True, "stored": True, "multiValued": False}
    ]


def test_a_solr_type_that_schema_xml_does_not_define_is_reported(solr, base):
    problems = solr.check(base, [field("zz_new", solr={"type": "no_such_type"})])

    assert problems and "no_such_type" in problems[0]


def test_the_solr_key_is_not_a_scheming_key_that_the_generator_rejects(generator):
    # the generator copies unknown keys of a field untouched, so a pack may carry a solr block
    assert "solr" not in generator.build_schema(["gdi_current"]).schema["dataset_fields"][0]


def test_schema_xml_is_read_with_its_fields_dynamic_fields_and_copy_fields(solr, base):
    assert base.fields["res_format"]["multiValued"] is True
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


def test_a_field_that_only_the_core_has_is_not_removed_unless_asked_for(solr):
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


# -- the fields nothing describes any more -------------------------------------------------------------


def test_a_field_that_nothing_describes_is_deleted_when_asked_for(solr):
    wanted = solr.SolrSchema(fields={"kept": spec("kept")}, field_types={"string"})
    live = live_schema(solr, kept=spec("kept"), old=spec("old"))

    commands, problems = solr.plan(wanted, live, remove_leftovers=True)

    assert commands == [("delete-field", {"name": "old"})] and problems == []


def test_the_copy_fields_of_a_deleted_field_go_first(solr):
    wanted = solr.SolrSchema(fields={"kept": spec("kept")}, copy_fields=[("kept", "text")], field_types={"string"})
    live = solr.SolrSchema(
        fields={"kept": spec("kept"), "old": spec("old")},
        copy_fields=[("kept", "text"), ("old", "text"), ("kept", "old")],
        field_types={"string"},
    )

    commands, _ = solr.plan(wanted, live, remove_leftovers=True)

    assert commands == [
        ("delete-copy-field", {"source": "old", "dest": "text"}),
        ("delete-copy-field", {"source": "kept", "dest": "old"}),
        ("delete-field", {"name": "old"}),
    ]


def test_the_fields_solr_keeps_for_itself_and_the_dynamic_fields_are_never_deleted(solr):
    wanted = solr.SolrSchema(field_types={"string"})
    live = solr.SolrSchema(
        fields={"_version_": spec("_version_"), "_root_": spec("_root_")},
        dynamic_fields={"old_*": spec("old_*")},
        field_types={"string"},
    )

    assert solr.plan(wanted, live, remove_leftovers=True)[0] == []


def test_the_fields_of_every_dataset_type_are_wanted_so_none_of_them_is_a_leftover(solr, base):
    dataset = [field("title"), field("keyword")]
    series = [field("series_order_field")]
    live = solr.SolrSchema(
        fields={**base.fields, "series_order_field": spec("series_order_field"), "old": spec("old")},
        field_types=set(base.field_types) | {"string"},
    )

    complete = solr.leftovers(solr.wanted_schema(base, solr.merge_fields([dataset, series])), live)
    partial = solr.leftovers(solr.wanted_schema(base, dataset), live)

    assert complete == ["old"]
    assert partial == ["old", "series_order_field"]


def test_the_first_definition_of_a_field_wins_when_the_types_share_it(solr):
    merged = solr.merge_fields([[field("a", "x")], [field("a"), field("b")], [None, {"x": 1}]])

    assert [f["field_name"] for f in merged] == ["a", "b"]
    assert merged[0]["repeating_subfields"]


def test_a_delete_is_described(solr):
    assert solr.describe(("delete-field", {"name": "old"})) == "delete-field old"


# -- the command line ----------------------------------------------------------------------------------


@pytest.fixture
def stack(solr, tmp_path, monkeypatch):
    """A CKAN ini with two dataset schemas, and a core that has one field too many; the commands sent are recorded."""
    (tmp_path / "dataset.yaml").write_text("dataset_fields:\n- field_name: keyword\n")
    (tmp_path / "series.yaml").write_text("dataset_fields:\n- field_name: series_order_field\n")
    ini = tmp_path / "ckan.ini"
    ini.write_text(
        "[app:main]\nuse = egg:ckan\nscheming.dataset_schemas = %s %s\n"
        % ((tmp_path / "dataset.yaml").as_uri(), (tmp_path / "series.yaml").as_uri())
    )
    live = solr.SolrSchema(
        fields={"keyword": spec("keyword"), "series_order_field": spec("series_order_field"), "old": spec("old")},
        field_types={"string"},
    )
    sent = []
    monkeypatch.setattr(solr, "wait_for_solr", lambda url, seconds: True)
    monkeypatch.setattr(solr, "read_live_schema", lambda url: live)
    monkeypatch.setattr(solr, "apply_commands", lambda url, commands: sent.extend(commands))
    # schema.xml of the test: nothing declared, so that only the dataset schemas count
    xml = tmp_path / "schema.xml"
    xml.write_text("<schema><types><fieldType name='string'/></types></schema>")

    class Stack:
        pass

    result = Stack()
    result.ini, result.dataset, result.series, result.xml, result.sent = ini, tmp_path / "dataset.yaml", tmp_path / "series.yaml", xml, sent
    return result


def sync(solr, stack, *args):
    return solr.main(["sync", "--schema-xml", str(stack.xml), "--solr-url", "http://solr/solr/ckan", *args])


def test_sync_removes_the_leftover_fields_of_the_stack(solr, stack, capsys):
    code = sync(solr, stack, "--ckan-ini", str(stack.ini))

    assert code == 0
    assert stack.sent == [("delete-field", {"name": "old"})]
    assert "delete-field old" in capsys.readouterr().out


def test_sync_with_a_dry_run_applies_nothing(solr, stack, capsys):
    sync(solr, stack, "--ckan-ini", str(stack.ini), "--dry-run")

    assert stack.sent == []
    assert "delete-field old" in capsys.readouterr().out


def test_sync_keeps_the_leftovers_when_asked_to(solr, stack):
    sync(solr, stack, "--ckan-ini", str(stack.ini), "--keep-leftovers")

    assert stack.sent == []


def test_sync_keeps_the_leftovers_when_it_does_not_know_every_schema(solr, stack, capsys):
    """Only one schema file: the fields of the others would look like leftovers."""
    code = sync(solr, stack, "--dataset-schema", str(stack.dataset))

    assert code == 0
    assert stack.sent == []
    assert "--ckan-ini" in capsys.readouterr().out


def test_sync_stops_when_a_schema_of_the_ini_cannot_be_found(solr, stack, capsys):
    stack.series.unlink()

    code = sync(solr, stack, "--ckan-ini", str(stack.ini))

    assert code == 1
    assert stack.sent == []
    assert "not found" in capsys.readouterr().err


def test_sync_stops_without_a_schema(solr, stack, capsys):
    assert sync(solr, stack) == 1
    assert "no dataset schema" in capsys.readouterr().err


def test_an_ini_without_dataset_schemas_is_an_error(solr, tmp_path):
    ini = tmp_path / "ckan.ini"
    ini.write_text("[app:main]\nuse = egg:ckan\n")

    with pytest.raises(solr.SolrSchemaError, match="scheming.dataset_schemas"):
        solr.schema_files_from_ini(ini)


def test_a_module_reference_names_a_file_inside_the_package(solr, tmp_path):
    path = solr.schema_files_from_ini(_ini_with(tmp_path, "ckanext.gdi_userportal:scheming/schemas/dataset_series_r8.yaml"))[0]

    assert path.name == "dataset_series_r8.yaml" and path.is_file()


def test_a_module_that_cannot_be_found_is_an_error(solr, tmp_path):
    with pytest.raises(solr.SolrSchemaError, match="no_such_module"):
        solr.schema_files_from_ini(_ini_with(tmp_path, "no_such_module:schemas/x.yaml"))


def _ini_with(tmp_path, value):
    ini = tmp_path / "ckan.ini"
    ini.write_text("[app:main]\nscheming.dataset_schemas = %s\n" % value)
    return ini


def test_a_copy_field_that_schema_xml_still_declares_is_added_again_after_its_source_is_deleted(solr):
    """A field made explicit before a dynamic field covered it: the copy field must survive, with the dynamic field as source."""
    wanted = solr.SolrSchema(
        fields={"ngram": spec("ngram")},
        dynamic_fields={"vocab_*": spec("vocab_*")},
        copy_fields=[("vocab_x", "ngram")],
        field_types={"string"},
    )
    live = solr.SolrSchema(
        fields={"ngram": spec("ngram"), "vocab_x": spec("vocab_x")},
        dynamic_fields={"vocab_*": spec("vocab_*")},
        copy_fields=[("vocab_x", "ngram")],
        field_types={"string"},
    )

    commands, _ = solr.plan(wanted, live, remove_leftovers=True)

    assert commands == [
        ("delete-copy-field", {"source": "vocab_x", "dest": "ngram"}),
        ("delete-field", {"name": "vocab_x"}),
        ("add-copy-field", {"source": "vocab_x", "dest": "ngram"}),
    ]
