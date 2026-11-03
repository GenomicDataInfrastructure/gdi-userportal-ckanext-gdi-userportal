# SPDX-FileCopyrightText: 2026 Stichting Health-RI
#
# SPDX-License-Identifier: Apache-2.0

"""Generator behaviour, on synthetic packs so that no real profile decides the outcome."""

import json
import logging

import pytest
import yaml


def field(name, **extra):
    return {"field_name": name, "label": name.title(), **extra}


@pytest.fixture
def make_root(tmp_path):
    """Write packs, fragments and snippets under tmp_path and return the root."""

    def make(packs, fragments, snippets=None):
        for kind, entries in (("packs", packs), ("fragments", fragments), ("snippets", snippets or {})):
            (tmp_path / kind).mkdir(exist_ok=True)
            for name, content in entries.items():
                text = content if isinstance(content, str) else yaml.safe_dump(content, sort_keys=False)
                (tmp_path / kind / f"{name}.yaml").write_text(text)
        return tmp_path

    return make


def pack(name, fragments, redefines=(), rdf_profiles=("rdf_a",)):
    return {
        "name": name,
        "fragments": list(fragments),
        "rdf_profiles": list(rdf_profiles),
        "redefines": list(redefines),
    }


def names(schema, section="dataset_fields"):
    return [f["field_name"] for f in schema[section]]


# --- environment parsing ------------------------------------------------------------


@pytest.mark.parametrize("raw", [None, "", "   ", "\n"])
def test_unset_or_empty_profiles_mean_the_default(generator, raw):
    assert generator.parse_profiles(raw) == ["gdi_current"]


@pytest.mark.parametrize(
    "raw, expected",
    [
        ("a", ["a"]),
        ("a b", ["a", "b"]),
        ("a,b", ["a", "b"]),
        ("a, b ,c", ["a", "b", "c"]),
        (" a  b ", ["a", "b"]),
        ("a,", ["a"]),
    ],
)
def test_profiles_may_be_separated_by_commas_and_whitespace(generator, raw, expected):
    assert generator.parse_profiles(raw) == expected


@pytest.mark.parametrize("raw", [",", " , ,", ",,"])
def test_separators_only_is_an_error(generator, raw):
    with pytest.raises(generator.ProfileError, match="no profile name"):
        generator.parse_profiles(raw)


def test_a_duplicate_profile_is_an_error(generator):
    with pytest.raises(generator.ProfileError, match="twice: a"):
        generator.parse_profiles("a b a")


def test_the_main_profile_defaults_to_the_first(generator):
    assert generator.parse_main_profile(None, ["a", "b"]) == "a"
    assert generator.parse_main_profile("", ["a", "b"]) == "a"


def test_the_main_profile_can_be_any_enabled_profile(generator):
    assert generator.parse_main_profile("b", ["a", "b"]) == "b"


def test_a_main_profile_that_is_not_enabled_is_an_error(generator):
    with pytest.raises(generator.ProfileError, match="'c' is not an enabled profile. Enabled: a, b"):
        generator.parse_main_profile("c", ["a", "b"])


# --- unknown and malformed packs ----------------------------------------------------


def test_an_unknown_profile_lists_the_known_ones(generator, make_root):
    root = make_root({"a": pack("a", ["f"]), "b": pack("b", ["f"])}, {"f": {"dataset_fields": []}})

    with pytest.raises(generator.ProfileError, match="unknown metadata profile 'nope'. Known profiles: a, b"):
        generator.build_schema(["nope"], root)


@pytest.mark.parametrize("name", ["../etc/passwd", "A", "a b", "a/b", ".hidden", ""])
def test_a_profile_name_cannot_leave_the_packs_directory(generator, make_root, name):
    root = make_root({"a": pack("a", ["f"])}, {"f": {"dataset_fields": []}})

    with pytest.raises(generator.ProfileError, match="invalid profile name"):
        generator.build_schema([name], root)


def test_the_real_registry_knows_gdi_current(generator):
    assert "gdi_current" in generator.Registry().pack_names()


def test_a_manifest_must_carry_its_own_file_name(generator, make_root):
    root = make_root({"a": pack("other", ["f"])}, {"f": {"dataset_fields": []}})

    with pytest.raises(generator.ProfileError, match="'name' must be 'a'"):
        generator.build_schema(["a"], root)


def test_an_unknown_manifest_key_is_an_error(generator, make_root):
    root = make_root({"a": {**pack("a", ["f"]), "fragmnts": []}}, {"f": {"dataset_fields": []}})

    with pytest.raises(generator.ProfileError, match="unknown manifest keys: fragmnts"):
        generator.build_schema(["a"], root)


def test_a_pack_needs_fragments_and_rdf_profiles(generator, make_root):
    root = make_root({"a": {"name": "a", "rdf_profiles": ["x"]}}, {})

    with pytest.raises(generator.ProfileError, match="'fragments' is required"):
        generator.build_schema(["a"], root)


def test_a_missing_fragment_is_an_error(generator, make_root):
    root = make_root({"a": pack("a", ["missing"])}, {})

    with pytest.raises(generator.ProfileError, match="fragment 'missing' not found"):
        generator.build_schema(["a"], root)


def test_invalid_yaml_is_an_error(generator, make_root):
    root = make_root({"a": pack("a", ["f"])}, {"f": "dataset_fields: [unclosed"})

    with pytest.raises(generator.ProfileError, match="cannot read"):
        generator.build_schema(["a"], root)


def test_a_field_without_a_name_is_an_error(generator, make_root):
    root = make_root({"a": pack("a", ["f"])}, {"f": {"dataset_fields": [{"label": "No name"}]}})

    with pytest.raises(generator.ProfileError, match="needs a 'field_name'"):
        generator.build_schema(["a"], root)


# --- ordering -----------------------------------------------------------------------


def test_fields_follow_the_fragments_of_the_pack_in_order(generator, make_root):
    root = make_root(
        {"a": pack("a", ["f2", "f1"])},
        {"f1": {"dataset_fields": [field("one"), field("two")]}, "f2": {"dataset_fields": [field("zero")]}},
    )

    assert names(generator.build_schema(["a"], root).schema) == ["zero", "one", "two"]


def test_the_precedence_order_decides_the_form_order(generator, make_root):
    root = make_root(
        {"a": pack("a", ["fa"]), "b": pack("b", ["fb"])},
        {"fa": {"dataset_fields": [field("from_a")]}, "fb": {"dataset_fields": [field("from_b")]}},
    )

    assert names(generator.build_schema(["a", "b"], root).schema) == ["from_a", "from_b"]
    assert names(generator.build_schema(["b", "a"], root).schema) == ["from_b", "from_a"]


def test_a_shared_field_keeps_the_position_of_its_first_occurrence(generator, make_root):
    root = make_root(
        {"a": pack("a", ["fa"]), "b": pack("b", ["fb"])},
        {
            "fa": {"dataset_fields": [field("x"), field("shared")]},
            "fb": {"dataset_fields": [field("y"), field("shared"), field("z")]},
        },
    )

    assert names(generator.build_schema(["a", "b"], root).schema) == ["x", "shared", "y", "z"]


def test_a_fragment_shared_by_two_packs_is_merged_once(generator, make_root):
    root = make_root(
        {"a": pack("a", ["core", "only_a"]), "b": pack("b", ["core", "only_b"])},
        {
            "core": {"dataset_fields": [field("title")]},
            "only_a": {"dataset_fields": [field("a_extra")]},
            "only_b": {"dataset_fields": [field("b_extra")]},
        },
    )

    build = generator.build_schema(["a", "b"], root)

    assert names(build.schema) == ["title", "a_extra", "b_extra"]
    assert build.conflicts == []
    assert build.fields["dataset_fields.title"] == ["a", "b"]
    assert build.fields["dataset_fields.a_extra"] == ["a"]


def test_a_single_pack_alone_leaves_out_the_fields_of_the_other(generator, make_root):
    root = make_root(
        {"a": pack("a", ["core", "only_a"]), "b": pack("b", ["core", "only_b"])},
        {
            "core": {"dataset_fields": [field("title")]},
            "only_a": {"dataset_fields": [field("a_extra")]},
            "only_b": {"dataset_fields": [field("b_extra")]},
        },
    )

    assert names(generator.build_schema(["b"], root).schema) == ["title", "b_extra"]


def test_dataset_and_resource_fields_are_separate_namespaces(generator, make_root):
    root = make_root(
        {"a": pack("a", ["fa"]), "b": pack("b", ["fb"])},
        {
            "fa": {"dataset_fields": [field("url", label="Landing page")], "resource_fields": [field("url")]},
            "fb": {"dataset_fields": [field("url", label="Landing page")], "resource_fields": [field("url")]},
        },
    )

    build = generator.build_schema(["a", "b"], root)

    assert names(build.schema) == ["url"] and names(build.schema, "resource_fields") == ["url"]
    assert build.schema["dataset_fields"][0]["label"] == "Landing page"


def test_an_empty_section_is_kept_empty(generator, make_root):
    root = make_root({"a": pack("a", ["f"])}, {"f": {"dataset_fields": None}})

    assert generator.build_schema(["a"], root).schema == {"dataset_fields": []}


# --- conflicts ----------------------------------------------------------------------


def conflicting_root(make_root, a_redefines=(), b_redefines=()):
    return make_root(
        {"a": pack("a", ["fa"], redefines=a_redefines), "b": pack("b", ["fb"], redefines=b_redefines)},
        {
            "fa": {"dataset_fields": [field("shared", help_text="from a", preset="select")]},
            "fb": {"dataset_fields": [field("shared", help_text="from b", preset="select")]},
        },
    )


def test_identical_definitions_are_not_a_conflict(generator, make_root):
    root = make_root(
        {"a": pack("a", ["fa"]), "b": pack("b", ["fb"])},
        {"fa": {"dataset_fields": [field("shared")]}, "fb": {"dataset_fields": [field("shared")]}},
    )

    assert generator.build_schema(["a", "b"], root).conflicts == []


def test_an_undeclared_conflict_fails_and_names_the_field_the_packs_and_the_keys(generator, make_root):
    root = conflicting_root(make_root)

    with pytest.raises(generator.ProfileError) as error:
        generator.build_schema(["a", "b"], root)

    message = str(error.value)
    assert "'dataset_fields.shared'" in message
    assert "packs a, b" in message
    assert "differs in: help_text" in message
    assert "redefines" in message


def test_an_undeclared_conflict_fails_whatever_the_order(generator, make_root):
    root = conflicting_root(make_root)

    with pytest.raises(generator.ProfileError, match="packs b, a"):
        generator.build_schema(["b", "a"], root)


@pytest.mark.parametrize("declared_by", ["a", "b"])
def test_a_declared_conflict_is_decided_by_the_order_of_the_packs(generator, make_root, declared_by):
    root = conflicting_root(
        make_root,
        a_redefines=["dataset_fields.shared"] if declared_by == "a" else [],
        b_redefines=["dataset_fields.shared"] if declared_by == "b" else [],
    )

    first_wins = generator.build_schema(["a", "b"], root)
    second_wins = generator.build_schema(["b", "a"], root)

    assert first_wins.schema["dataset_fields"][0]["help_text"] == "from a"
    assert second_wins.schema["dataset_fields"][0]["help_text"] == "from b"
    assert first_wins.conflicts == [
        {"field": "dataset_fields.shared", "winner": "a", "losers": ["b"], "differing_keys": ["help_text"]}
    ]


def test_a_resolved_conflict_is_logged_as_a_warning(generator, make_root, caplog):
    root = conflicting_root(make_root, a_redefines=["dataset_fields.shared"])

    with caplog.at_level(logging.WARNING, logger="metadata-profiles"):
        generator.build_schema(["a", "b"], root)

    assert "'dataset_fields.shared' is defined differently by a, b; 'a' wins" in caplog.text


def test_a_conflict_does_not_arise_when_only_one_pack_is_enabled(generator, make_root):
    root = conflicting_root(make_root)

    assert generator.build_schema(["b"], root).schema["dataset_fields"][0]["help_text"] == "from b"


def test_redefining_a_field_the_pack_does_not_define_is_an_error(generator, make_root):
    root = make_root(
        {"a": pack("a", ["fa"], redefines=["dataset_fields.typo"])},
        {"fa": {"dataset_fields": [field("shared")]}},
    )

    with pytest.raises(generator.ProfileError, match="redefines 'dataset_fields.typo' but does not define it"):
        generator.build_schema(["a"], root)


def test_one_pack_cannot_define_a_field_twice_differently(generator, make_root):
    root = make_root(
        {"a": pack("a", ["f1", "f2"], redefines=["dataset_fields.shared"])},
        {
            "f1": {"dataset_fields": [field("shared", help_text="one")]},
            "f2": {"dataset_fields": [field("shared", help_text="two")]},
        },
    )

    with pytest.raises(generator.ProfileError, match="fragments 'f1' and 'f2' of pack 'a'"):
        generator.build_schema(["a"], root)


def test_true_and_one_are_different_definitions(generator, make_root):
    root = make_root(
        {"a": pack("a", ["fa"]), "b": pack("b", ["fb"])},
        {
            "fa": {"dataset_fields": [field("flag", default=True)]},
            "fb": {"dataset_fields": [field("flag", default=1)]},
        },
    )

    with pytest.raises(generator.ProfileError, match="differs in: default"):
        generator.build_schema(["a", "b"], root)


def test_header_keys_merge_as_a_whole_and_conflict_like_fields(generator, make_root):
    root = make_root(
        {"a": pack("a", ["fa"]), "b": pack("b", ["fb"])},
        {
            "fa": {"form_languages": ["en"], "dataset_fields": []},
            "fb": {"form_languages": ["en", "nl"], "dataset_fields": []},
        },
    )

    with pytest.raises(generator.ProfileError, match="'form_languages' is defined differently"):
        generator.build_schema(["a", "b"], root)


def test_a_declared_header_conflict_is_decided_by_the_order(generator, make_root):
    root = make_root(
        {"a": pack("a", ["fa"], redefines=["form_languages"]), "b": pack("b", ["fb"])},
        {"fa": {"form_languages": ["en"]}, "fb": {"form_languages": ["en", "nl"]}},
    )

    assert generator.build_schema(["a", "b"], root).schema["form_languages"] == ["en"]


# --- snippets -----------------------------------------------------------------------


def test_a_snippet_is_expanded_where_it_is_used(generator, make_root):
    root = make_root(
        {"a": pack("a", ["f"])},
        {"f": "dataset_fields:\n  - field_name: x\n    repeating_subfields: !snippet agent\n"},
        snippets={"agent": [field("uri"), field("name")]},
    )

    schema = generator.build_schema(["a"], root).schema

    assert schema["dataset_fields"][0]["repeating_subfields"] == [field("uri"), field("name")]


def test_a_snippet_used_twice_is_rendered_without_aliases(generator, make_root):
    root = make_root(
        {"a": pack("a", ["f"])},
        {
            "f": "dataset_fields:\n"
            "  - {field_name: x, repeating_subfields: !snippet agent}\n"
            "  - {field_name: y, repeating_subfields: !snippet agent}\n"
        },
        snippets={"agent": [field("uri")]},
    )

    rendered = generator.render_schema(generator.build_schema(["a"], root).schema)

    assert "&id" not in rendered and "*id" not in rendered
    assert rendered.count("field_name: uri") == 2


def test_a_missing_snippet_is_an_error(generator, make_root):
    root = make_root({"a": pack("a", ["f"])}, {"f": "dataset_fields:\n  - {field_name: x, extra: !snippet nope}\n"})

    with pytest.raises(generator.ProfileError, match="snippet 'nope' not found"):
        generator.build_schema(["a"], root)


def test_a_snippet_cannot_reference_another_snippet(generator, make_root):
    root = make_root(
        {"a": pack("a", ["f"])},
        {"f": "dataset_fields:\n  - {field_name: x, extra: !snippet outer}\n"},
        snippets={"outer": "- !snippet inner\n", "inner": [field("uri")]},
    )

    with pytest.raises(generator.ProfileError, match="may not reference other snippets"):
        generator.build_schema(["a"], root)


# --- output -------------------------------------------------------------------------


def test_the_config_options_for_the_default_profile(generator, tmp_path):
    build = generator.build_schema(["gdi_current"])
    schema_path = tmp_path / "dataset.yaml"

    options = generator.config_options(build, "gdi_current", schema_path)

    assert options == [
        "ckanext.dcat.metadata_profiles = gdi_current",
        "ckanext.dcat.metadata_profiles.main = gdi_current",
        "ckanext.dcat.metadata_profiles.gdi_current.rdf_profiles = fairdatapoint_dcat_ap euro_dcat_ap_nl",
        "ckanext.dcat.rdf.profiles = fairdatapoint_dcat_ap euro_dcat_ap_nl",
        f"scheming.dataset_schemas = {schema_path.resolve().as_uri()} "
        "ckanext.gdi_userportal:scheming/schemas/dataset_series_multilingual.yaml",
        "scheming.presets = ckanext.scheming:presets.json ckanext.dcat.schemas:presets.yaml "
        "ckanext.fluent:presets.json ckanext.gdi_userportal:scheming/presets/gdi_presets.yaml "
        "ckanext.dataset_series.schemas:presets.yaml",
    ]


def test_the_main_profile_decides_the_rdf_profile_chain(generator, make_root, tmp_path):
    root = make_root(
        {"a": pack("a", ["f"], rdf_profiles=["rdf_a"]), "b": pack("b", ["f"], rdf_profiles=["rdf_b1", "rdf_b2"])},
        {"f": {"dataset_fields": [field("x")]}},
    )
    build = generator.build_schema(["a", "b"], root)

    options = generator.config_options(build, "b", tmp_path / "dataset.yaml")

    assert "ckanext.dcat.metadata_profiles = a b" in options
    assert "ckanext.dcat.rdf.profiles = rdf_b1 rdf_b2" in options
    assert "ckanext.dcat.metadata_profiles.a.rdf_profiles = rdf_a" in options


def test_generation_is_deterministic(generator, tmp_path):
    first = tmp_path / "one"
    second = tmp_path / "two"

    generator.generate(None, None, first)
    generator.generate(None, None, second)
    generator.generate(None, None, first)

    for name in ("dataset.yaml", "provenance.json"):
        assert (first / name).read_bytes() == (second / name).read_bytes()
    assert sorted(p.name for p in first.iterdir()) == ["dataset.yaml", "provenance.json"]


def test_the_generated_file_is_readable_by_other_users(generator, tmp_path):
    generator.generate(None, None, tmp_path / "out")

    assert (tmp_path / "out" / "dataset.yaml").stat().st_mode & 0o777 == 0o644
    assert (tmp_path / "out").stat().st_mode & 0o777 == 0o755


def test_the_provenance_records_which_packs_define_each_field(generator, tmp_path):
    generator.generate("gdi_current", None, tmp_path)
    provenance = json.loads((tmp_path / "provenance.json").read_text())

    assert provenance["profiles"] == ["gdi_current"] and provenance["main"] == "gdi_current"
    assert provenance["fields"]["dataset_fields.trusted_data_holder"] == ["gdi_current"]
    assert provenance["conflicts"] == []


def test_a_failed_generation_leaves_no_files(generator, tmp_path):
    with pytest.raises(generator.ProfileError):
        generator.generate("nope", None, tmp_path / "out")

    assert not (tmp_path / "out").exists()


# --- RDF profile check --------------------------------------------------------------


def test_an_rdf_profile_that_is_not_installed_is_an_error(generator):
    build = generator.build_schema(["gdi_current"])

    with pytest.raises(
        generator.ProfileError, match="'gdi_current' needs RDF profiles that are not installed: euro_dcat_ap_nl"
    ):
        generator.check_rdf_profiles(build, installed={"fairdatapoint_dcat_ap"})


def test_installed_rdf_profiles_pass_the_check(generator):
    build = generator.build_schema(["gdi_current"])

    generator.check_rdf_profiles(build, installed={"fairdatapoint_dcat_ap", "euro_dcat_ap_nl", "other"})


# --- command line -------------------------------------------------------------------


def test_the_command_line_prints_the_config_options(generator, tmp_path, capsys):
    status = generator.main(["--output-dir", str(tmp_path), "--skip-entry-point-check"], environ={})

    out = capsys.readouterr().out.splitlines()
    assert status == 0
    assert out[0] == "ckanext.dcat.metadata_profiles = gdi_current"
    assert out[-2].startswith("scheming.dataset_schemas = file://")
    assert out[-1].startswith("scheming.presets = ")


def test_the_command_line_reads_the_environment(generator, tmp_path, capsys):
    status = generator.main(
        ["--output-dir", str(tmp_path), "--skip-entry-point-check"],
        environ={"GDI_METADATA_PROFILES": "nope"},
    )

    assert status == 1
    assert "unknown metadata profile 'nope'. Known profiles: gdi_current" in capsys.readouterr().err


def test_an_unknown_profile_is_reported_before_the_main_profile(generator, tmp_path, capsys):
    status = generator.main(
        ["--output-dir", str(tmp_path), "--skip-entry-point-check"],
        environ={"GDI_METADATA_PROFILES": "nope", "GDI_METADATA_MAIN_PROFILE": "gdi_current"},
    )

    assert status == 1
    assert "unknown metadata profile 'nope'" in capsys.readouterr().err


def test_empty_environment_values_mean_the_default(generator, tmp_path, capsys):
    status = generator.main(
        ["--output-dir", str(tmp_path), "--skip-entry-point-check"],
        environ={"GDI_METADATA_PROFILES": "", "GDI_METADATA_MAIN_PROFILE": ""},
    )

    assert status == 0
    assert capsys.readouterr().out.splitlines()[0] == "ckanext.dcat.metadata_profiles = gdi_current"


def test_the_command_line_fails_on_a_main_profile_that_is_not_enabled(generator, tmp_path, capsys):
    status = generator.main(
        ["--output-dir", str(tmp_path), "--skip-entry-point-check"],
        environ={"GDI_METADATA_MAIN_PROFILE": "healthdcat_r8"},
    )

    assert status == 1
    assert "'healthdcat_r8' is not an enabled profile. Enabled: gdi_current" in capsys.readouterr().err


def test_the_command_line_checks_the_installed_rdf_profiles_by_default(generator, tmp_path, capsys, monkeypatch):
    monkeypatch.setattr(generator, "installed_rdf_profiles", lambda: set())

    status = generator.main(["--output-dir", str(tmp_path)], environ={})

    assert status == 1
    assert "not installed: fairdatapoint_dcat_ap, euro_dcat_ap_nl" in capsys.readouterr().err


def test_the_generator_imports_with_only_stdlib_and_pyyaml(generator):
    import ast
    import sys

    tree = ast.parse((generator.PACK_ROOT / "generator.py").read_text())
    imported = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.level == 0:
            imported.add(node.module.split(".")[0])

    assert {name for name in imported if name not in sys.stdlib_module_names and name != "yaml"} == set()


# --- retired fields (the prune command) ------------------------------------------------


def retirement_root(make_root, b_keep=(), b_extra_fields=()):
    return make_root(
        {
            "a": pack("a", ["fa"]),
            "b": {**pack("b", ["fa", "fb"]), "keep_extras": list(b_keep)},
            "c": pack("c", ["fc"]),
        },
        {
            "fa": {"dataset_fields": [field("shared")]},
            "fb": {
                "dataset_fields": [field("only_b"), field("kept_b"), *b_extra_fields],
                "resource_fields": [field("res_b")],
            },
            "fc": {"dataset_fields": [field("only_c"), field("only_b")]},
        },
    )


def test_a_field_only_retired_packs_define_is_retired_with_the_packs_that_define_it(generator, make_root):
    retired = generator.retired_fields(["a"], retirement_root(make_root))
    assert retired["dataset_fields"] == {"only_b": ["b", "c"], "kept_b": ["b"], "only_c": ["c"]}
    assert retired["resource_fields"] == {"res_b": ["b"]}


def test_a_field_an_enabled_pack_defines_is_never_retired(generator, make_root):
    # c defines only_c and only_b; a and b are retired, and only they define shared and kept_b
    retired = generator.retired_fields(["c"], retirement_root(make_root))
    assert set(retired["dataset_fields"]) == {"shared", "kept_b"}


def test_the_shared_field_stays_while_any_pack_that_defines_it_is_enabled(generator, make_root):
    root = retirement_root(make_root)
    for enabled in (["a"], ["b"], ["a", "b"]):
        assert "shared" not in generator.retired_fields(enabled, root)["dataset_fields"]


def test_enabling_every_pack_retires_nothing(generator, make_root):
    assert generator.retired_fields(["a", "b", "c"], retirement_root(make_root)) == {
        "dataset_fields": {},
        "resource_fields": {},
    }


def test_keep_extras_are_left_out_of_the_retired_fields(generator, make_root):
    retired = generator.retired_fields(["a"], retirement_root(make_root, b_keep=["kept_b"]))
    assert "kept_b" not in retired["dataset_fields"]
    assert "only_b" in retired["dataset_fields"]


def test_keeping_an_extra_the_pack_does_not_define_is_an_error(generator, make_root):
    with pytest.raises(generator.ProfileError, match="keeps the extra 'ghost' but does not define it"):
        generator.build_schema(["b"], retirement_root(make_root, b_keep=["ghost"]))


def test_an_unknown_enabled_pack_is_reported(generator, make_root):
    with pytest.raises(generator.ProfileError, match="unknown metadata profile 'nope'"):
        generator.retired_fields(["nope"], retirement_root(make_root))


# --- conformance files ------------------------------------------------------------------

ALL_LAYERS = ("PUBLIC", "RESTRICTED", "NON_PUBLIC")


def conformance_document(layers=None):
    body = {"mandatory": [{"property": "title", "fields": ["title_translated"]}]}
    return {"profile": "a", "layers": layers or {layer: body for layer in ALL_LAYERS}}


def root_with_conformance(make_root, document, manifest_path="conformance/a.json"):
    root = make_root({"a": {**pack("a", ["fa"]), "conformance": manifest_path}}, {"fa": {"dataset_fields": [field("x")]}})
    if document is not None:
        (root / "conformance").mkdir(exist_ok=True)
        (root / "conformance" / "a.json").write_text(document if isinstance(document, str) else json.dumps(document))
    return root


def test_a_pack_loads_its_conformance_file(generator, make_root):
    registry = generator.Registry(root_with_conformance(make_root, conformance_document()))
    rules = registry.conformance(registry.pack("a"))
    assert [r["property"] for r in rules["layers"]["PUBLIC"]["mandatory"]] == ["title"]


def test_a_pack_without_a_conformance_file_has_no_rules(generator, make_root):
    root = make_root({"a": pack("a", ["fa"])}, {"fa": {"dataset_fields": [field("x")]}})
    registry = generator.Registry(root)
    assert registry.conformance(registry.pack("a")) is None


@pytest.mark.parametrize(
    "document, message",
    [
        (None, "cannot read the conformance file"),
        ("not json", "cannot read the conformance file"),
        ("[]", "expected 'layers'"),
        (conformance_document({"PUBLIC": {"mandatory": []}}), "expected 'layers' with exactly"),
        (conformance_document({layer: {"mandatory": "x"} for layer in ALL_LAYERS}), "needs a 'mandatory' list"),
        (
            conformance_document({layer: {"mandatory": [{"property": "t", "fields": []}]} for layer in ALL_LAYERS}),
            "needs a 'mandatory' list",
        ),
    ],
)
def test_a_broken_conformance_file_is_reported_when_loaded(generator, make_root, document, message):
    registry = generator.Registry(root_with_conformance(make_root, document))
    with pytest.raises(generator.ProfileError, match=message):
        registry.conformance(registry.pack("a"))


def test_a_conformance_path_cannot_leave_the_pack_root(generator, make_root):
    root = root_with_conformance(make_root, conformance_document(), manifest_path="../outside.json")
    registry = generator.Registry(root)
    with pytest.raises(generator.ProfileError, match="outside"):
        registry.conformance(registry.pack("a"))


def test_the_conformance_manifest_key_must_be_a_string(generator, make_root):
    root = make_root({"a": {**pack("a", ["fa"]), "conformance": ["x"]}}, {"fa": {"dataset_fields": [field("x")]}})
    with pytest.raises(generator.ProfileError, match="'conformance' must be a path"):
        generator.Registry(root).pack("a")


# --- series schema ------------------------------------------------------------------


def test_the_series_schema_of_the_first_pack_that_has_one_decides(generator, make_root):
    root = make_root(
        {
            "a": {**pack("a", ["fa"]), "series_schema": "pkg.mod:schemas/a.yaml"},
            "b": {**pack("b", ["fb"]), "series_schema": "pkg.mod:schemas/b.yaml"},
            "c": pack("c", ["fb"]),
        },
        {"fa": {"dataset_fields": [field("x")]}, "fb": {"dataset_fields": [field("y")]}},
    )
    registry = generator.Registry(root)

    def series(*profiles):
        return generator.build_schema(list(profiles), root=root).series_schema

    assert series("a", "b") == "pkg.mod:schemas/a.yaml"
    assert series("b", "a") == "pkg.mod:schemas/b.yaml"
    assert series("c", "b") == "pkg.mod:schemas/b.yaml"
    assert series("c") is None
    assert registry.pack("c").series_schema is None


def test_the_series_schema_goes_into_the_scheming_options(generator, make_root, tmp_path):
    root = make_root(
        {"a": {**pack("a", ["fa"]), "series_schema": "pkg.mod:schemas/a.yaml"}, "c": pack("c", ["fa"])},
        {"fa": {"dataset_fields": [field("x")]}},
    )

    with_series = generator.config_options(generator.build_schema(["a"], root=root), "a", tmp_path / "dataset.yaml")
    without = generator.config_options(generator.build_schema(["c"], root=root), "c", tmp_path / "dataset.yaml")

    assert any(o.startswith("scheming.dataset_schemas") and o.endswith(" pkg.mod:schemas/a.yaml") for o in with_series)
    assert any(o.startswith("scheming.dataset_schemas") and o.endswith(generator.STATIC_SCHEMAS[0]) for o in without)


@pytest.mark.parametrize("value", [1, "schema.yaml", "pkg:schema.txt", "../x:y.yaml", ["a:b.yaml"]])
def test_a_series_schema_must_be_a_schema_reference(generator, make_root, value):
    root = make_root({"a": {**pack("a", ["fa"]), "series_schema": value}}, {"fa": {"dataset_fields": [field("x")]}})

    with pytest.raises(generator.ProfileError, match="series_schema"):
        generator.Registry(root).pack("a")

