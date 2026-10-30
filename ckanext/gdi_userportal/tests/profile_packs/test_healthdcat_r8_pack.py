# SPDX-FileCopyrightText: 2026 Stichting Health-RI
#
# SPDX-License-Identifier: Apache-2.0

"""
The real ``healthdcat_r8`` pack, alone and next to ``gdi_current``.

The generator is tested on synthetic packs in ``test_generator.py``; here the shipped packs
have to generate valid schemas in every mode, and the fields they share have to be shared.
"""

import pytest

GDI_ONLY = {"dataset_status", "trusted_data_holder"}
R8_ONLY = {
    "alternative_title",
    "related_resource",
    "source",
    "has_structured_data",
    "variables",
    "custodian",
    "hdab_coordinator",
}
MODES = [
    ["gdi_current"],
    ["healthdcat_r8"],
    ["gdi_current", "healthdcat_r8"],
    ["healthdcat_r8", "gdi_current"],
]


def names(fields):
    return [f["field_name"] for f in fields]


def dataset_fields(generator, profiles):
    return {f["field_name"]: f for f in generator.build_schema(profiles).schema["dataset_fields"]}


def walk(fields, path=""):
    """Yield (path, field) for every field and subfield."""
    for field in fields:
        here = f"{path}.{field['field_name']}" if path else field["field_name"]
        yield here, field
        yield from walk(field.get("repeating_subfields", []), here)


@pytest.mark.parametrize("profiles", MODES, ids=" + ".join)
def test_every_mode_generates_a_schema(generator, profiles):
    schema = generator.build_schema(profiles).schema

    assert names(schema["dataset_fields"]), "no dataset fields"
    assert names(schema["resource_fields"]), "no resource fields"


@pytest.mark.parametrize("profiles", MODES, ids=" + ".join)
def test_no_mode_has_a_conflict_left_unresolved(generator, profiles):
    assert generator.build_schema(profiles).conflicts == []


@pytest.mark.parametrize("profiles", MODES, ids=" + ".join)
def test_field_names_are_unique_within_their_parent(generator, profiles):
    schema = generator.build_schema(profiles).schema

    def check(fields, where):
        seen = names(fields)
        assert len(seen) == len(set(seen)), f"duplicate field name under {where}"
        for f in fields:
            check(f.get("repeating_subfields", []), f"{where}.{f['field_name']}")

    check(schema["dataset_fields"], "dataset_fields")
    check(schema["resource_fields"], "resource_fields")


@pytest.mark.parametrize("profiles", MODES, ids=" + ".join)
def test_every_field_and_subfield_has_a_label_or_a_preset_that_supplies_one(generator, profiles):
    schema = generator.build_schema(profiles).schema

    for section in ("dataset_fields", "resource_fields"):
        for path, field in walk(schema[section]):
            assert field.get("label") or field.get("preset"), f"{section}.{path} has neither a label nor a preset"


@pytest.mark.parametrize("profiles", MODES, ids=" + ".join)
def test_nothing_is_required(generator, profiles):
    """Conformance is computed, never enforced (ADR 0001)."""
    schema = generator.build_schema(profiles).schema

    for section in ("dataset_fields", "resource_fields"):
        for path, field in walk(schema[section]):
            assert not field.get("required"), f"{section}.{path} is required"


def test_r8_alone_adds_the_r8_fields_and_leaves_out_the_gdi_ones(generator):
    r8 = set(dataset_fields(generator, ["healthdcat_r8"]))
    gdi = set(dataset_fields(generator, ["gdi_current"]))

    assert R8_ONLY <= r8
    assert not GDI_ONLY & r8
    assert gdi - GDI_ONLY <= r8


def test_gdi_current_alone_has_none_of_the_r8_fields(generator):
    gdi = set(dataset_fields(generator, ["gdi_current"]))

    assert not R8_ONLY & gdi
    assert GDI_ONLY <= gdi


@pytest.mark.parametrize("profiles", MODES[2:], ids=" + ".join)
def test_both_packs_give_the_union_of_their_fields(generator, profiles):
    both = set(dataset_fields(generator, profiles))

    assert both == set(dataset_fields(generator, ["gdi_current"])) | set(dataset_fields(generator, ["healthdcat_r8"]))


def test_with_gdi_current_first_its_form_order_is_kept(generator):
    both = list(dataset_fields(generator, ["gdi_current", "healthdcat_r8"]))
    gdi = list(dataset_fields(generator, ["gdi_current"]))

    assert both[: len(gdi)] == gdi


def test_the_r8_fields_are_defined_by_the_r8_pack_only(generator):
    build = generator.build_schema(["gdi_current", "healthdcat_r8"])

    for name in R8_ONLY:
        assert build.fields[f"dataset_fields.{name}"] == ["healthdcat_r8"]
    for name in GDI_ONLY:
        assert build.fields[f"dataset_fields.{name}"] == ["gdi_current"]
    assert build.fields["dataset_fields.title_translated"] == ["gdi_current", "healthdcat_r8"]


def test_the_r8_pack_has_its_own_rdf_profile(generator):
    build = generator.build_schema(["gdi_current", "healthdcat_r8"])

    assert build.rdf_profiles["healthdcat_r8"] == ["euro_health_dcat_ap_r8"]
    assert build.rdf_profiles["gdi_current"] == ["fairdatapoint_dcat_ap", "euro_dcat_ap_nl"]


def test_the_main_profile_decides_the_default_chain(generator, tmp_path):
    build = generator.build_schema(["gdi_current", "healthdcat_r8"])

    options = generator.config_options(build, "healthdcat_r8", tmp_path / "dataset.yaml")

    assert "ckanext.dcat.rdf.profiles = euro_health_dcat_ap_r8" in options
    assert "ckanext.dcat.metadata_profiles.gdi_current.rdf_profiles = fairdatapoint_dcat_ap euro_dcat_ap_nl" in options


def test_custodian_and_the_coordinator_have_the_subfields_of_hdab(generator):
    fields = dataset_fields(generator, ["healthdcat_r8"])

    hdab = names(fields["hdab"]["repeating_subfields"])
    assert names(fields["custodian"]["repeating_subfields"]) == hdab
    assert names(fields["hdab_coordinator"]["repeating_subfields"]) == hdab


def test_has_structured_data_is_a_boolean_like_trusted_data_holder(generator):
    fields = dataset_fields(generator, ["gdi_current", "healthdcat_r8"])
    flag, existing = fields["has_structured_data"], fields["trusted_data_holder"]

    for key in ("preset", "choices", "validators", "output_validators"):
        assert flag[key] == existing[key]


def test_variables_nest_table_group_table_and_column(generator):
    group = dataset_fields(generator, ["healthdcat_r8"])["variables"]
    table = next(f for f in group["repeating_subfields"] if f["field_name"] == "tables")
    column = next(f for f in table["repeating_subfields"] if f["field_name"] == "columns")

    assert {"title_translated", "tables"} <= set(names(group["repeating_subfields"]))
    assert {"title_translated", "keyword", "url", "columns"} <= set(names(table["repeating_subfields"]))
    assert {"name", "title_translated", "description_translated", "datatype", "property_url"} <= set(
        names(column["repeating_subfields"])
    )


def test_related_resource_and_source_keep_the_key_of_the_existing_extras(generator):
    """No backfill: values saved as free extras become field values in place."""
    assert {"related_resource", "source"} <= set(dataset_fields(generator, ["healthdcat_r8"]))
