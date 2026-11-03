# SPDX-FileCopyrightText: 2026 Stichting Health-RI
#
# SPDX-License-Identifier: Apache-2.0

"""
The real ``healthdcat_r8`` pack, alone and next to ``gdi_current``.

The generator is tested on synthetic packs in ``test_generator.py``; here the shipped packs
have to generate valid schemas in every mode, and the fields they share have to be shared.
"""

import pytest
import yaml

# What only gdi_current has. publisher_note and publisher_type on the dataset are the HealthDCAT-AP
# ones (R8 has the note on the publisher only); the license is on the distributions in R8.
GDI_ONLY = {"dataset_status", "trusted_data_holder", "publisher_note", "publisher_type", "license_id"}
GDI_ONLY_RESOURCE = {"retention_period"}
R8_ONLY_RESOURCE = {"has_policy"}
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


# Shared fields R8 defines differently. The pack declares them, so that the pack listed first decides.
REDEFINED = {
    "dataset_fields.contact",
    "dataset_fields.spatial_coverage",
    "dataset_fields.publisher",
    "dataset_fields.creator",
    "dataset_fields.qualified_attribution",
    "dataset_fields.was_generated_by",
    "dataset_fields.hdab",
    "dataset_fields.qualified_relation",
    "dataset_fields.spatial_resolution_in_meters",
    "dataset_fields.retention_period",
    "resource_fields.spatial_resolution_in_meters",
    "dataset_fields.url",
    "dataset_fields.dcat_type",
    "resource_fields.access_services",
    "resource_fields.name_translated",
    "resource_fields.compress_format",
    "resource_fields.package_format",
    "resource_fields.size",
    "resource_fields.hash",
    "resource_fields.hash_algorithm",
    "resource_fields.license",
    "resource_fields.conforms_to",
}
# R8 agents (HealthDCAT-AP R8, Agent_Shape and the health agent shapes): a name and a type, the
# health agents of a dataset add the contact point and the publisher a description.
AGENT = {"uri", "name", "name_translated", "type"}
CONTACT_POINT = {"email", "url", "telephone", "opening_hours", "special_opening_hours"}
# dct:Location: the location is an IRI, with a geometry, a bounding box and a centroid
LOCATION = {"uri", "geom", "bbox", "centroid"}
# dcat:DataService, from the data service table of the R8 gap analysis
DATA_SERVICE = {
    "uri", "title", "description", "theme", "endpoint_description", "endpoint_url", "serves_dataset",
    "access_rights", "conforms_to", "format", "landing_page", "documentation", "keyword",
    "keyword_translated", "applicable_legislation", "contact", "publisher", "license",
}
CONTACT_POINT_SUBFIELDS = ["telephone", "opening_hours", "special_opening_hours"]


@pytest.mark.parametrize("profiles", MODES[:2], ids=" + ".join)
def test_one_pack_alone_has_no_conflict(generator, profiles):
    assert generator.build_schema(profiles).conflicts == []


@pytest.mark.parametrize("profiles", MODES[2:], ids=" + ".join)
def test_both_packs_conflict_on_the_redefined_fields_only_and_all_are_declared(generator, profiles):
    conflicts = generator.build_schema(profiles).conflicts

    assert {c["field"] for c in conflicts} == REDEFINED
    assert all(c["winner"] == profiles[0] for c in conflicts)


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


def subfield_names(field):
    return names(field["repeating_subfields"])


def test_custodian_and_the_coordinator_have_the_subfields_of_hdab(generator):
    fields = dataset_fields(generator, ["healthdcat_r8"])

    assert subfield_names(fields["custodian"]) == subfield_names(fields["hdab"])
    assert subfield_names(fields["hdab_coordinator"]) == subfield_names(fields["hdab"])


def subfields_of(field, *path):
    for name in path:
        field = next(f for f in field["repeating_subfields"] if f["field_name"] == name)
    return field


def test_r8_agents_have_only_the_properties_of_the_r8_model(generator):
    fields = dataset_fields(generator, ["healthdcat_r8"])

    assert set(subfield_names(fields["creator"])) == AGENT
    assert set(subfield_names(subfields_of(fields["qualified_attribution"], "agent"))) == AGENT
    assert set(subfield_names(fields["publisher"])) == AGENT | CONTACT_POINT | {"publisher_note"}
    for name in ("hdab", "custodian", "hdab_coordinator"):
        assert set(subfield_names(fields[name])) == AGENT | CONTACT_POINT, name


def test_the_r8_activity_has_a_label_and_a_type_and_gdi_current_keeps_the_rest(generator):
    r8 = dataset_fields(generator, ["healthdcat_r8"])["was_generated_by"]
    gdi = dataset_fields(generator, ["gdi_current"])["was_generated_by"]

    assert subfield_names(r8) == ["uri", "label", "type", "dct_type"]
    assert {"seeAlso", "startedAtTime", "wasAssociatedWith"} <= set(subfield_names(gdi))


def test_the_email_contact_page_and_telephone_of_a_contact_point_are_lists_in_r8(generator):
    """cv:ContactPoint: cv:email, cv:contactPage and cv:telephone are 0..n."""
    fields = dataset_fields(generator, ["healthdcat_r8"])

    for name in ("publisher", "hdab", "custodian", "hdab_coordinator"):
        for sub in ("email", "url", "telephone"):
            assert "multiple_text" in str(subfields_of(fields[name], sub)), f"{name}.{sub}"
    gdi = dataset_fields(generator, ["gdi_current"])
    for sub in ("email", "url"):
        assert "multiple_text" not in str(subfields_of(gdi["publisher"], sub)), sub


def test_a_location_in_r8_has_no_label_and_gdi_current_keeps_it(generator):
    r8 = dataset_fields(generator, ["healthdcat_r8"])["spatial_coverage"]
    gdi = dataset_fields(generator, ["gdi_current"])["spatial_coverage"]

    assert set(subfield_names(r8)) == LOCATION
    assert "text" in subfield_names(gdi)


def test_the_contact_point_of_a_dataset_keeps_its_name_in_gdi_current(generator):
    gdi = dataset_fields(generator, ["gdi_current"])["contact"]

    assert {"name", "name_translated", "identifier"} <= set(subfield_names(gdi))


def test_the_note_of_the_r8_publisher_is_its_description(generator):
    note = subfields_of(dataset_fields(generator, ["healthdcat_r8"])["publisher"], "publisher_note")

    # R8 reads dct:description into the same key, so the key stays and only the label tells R8 apart
    assert note["label"] == "Description"


def test_the_contact_page_of_an_r8_agent_is_labelled_as_such(generator):
    fields = dataset_fields(generator, ["healthdcat_r8"])

    for name in ("publisher", "hdab", "custodian", "hdab_coordinator"):
        assert subfields_of(fields[name], "url")["label"] == "Contact page", name


def test_an_r8_contact_point_has_one_email_and_one_contact_page(generator):
    contact = dataset_fields(generator, ["healthdcat_r8"])["contact"]
    url = subfields_of(contact, "url")

    assert set(subfield_names(contact)) == {"uri", "email", "url"}, "vcard:Kind has an email and a contact page"
    assert "multiple_text" not in str(url), "vcard:Kind allows one vcard:hasURL"


def test_gdi_current_keeps_what_r8_leaves_out_of_the_agents_and_the_contact(generator):
    fields = dataset_fields(generator, ["gdi_current"])

    for name in ("creator", "publisher", "hdab"):
        assert {"identifier", "country"} <= set(subfield_names(fields[name])), name
    assert {"publisher_note", "publisher_type"} <= set(subfield_names(fields["creator"]))
    assert {"publisher_note", "publisher_type"} <= set(subfield_names(fields["publisher"]))
    assert {"publisher_note", "publisher_type", "license_id"} <= set(fields)
    assert "multiple_text" in str(subfields_of(fields["contact"], "url"))


def test_r8_has_no_legacy_publisher_fields_and_no_dataset_license(generator):
    fields = dataset_fields(generator, ["healthdcat_r8"])

    assert not {"publisher_note", "publisher_type", "license_id"} & set(fields)


def test_the_r8_distribution_has_no_retention_period_and_gdi_current_keeps_it(generator):
    def resource_names(profiles):
        return set(names(generator.build_schema(profiles).schema["resource_fields"]))

    assert not GDI_ONLY_RESOURCE & resource_names(["healthdcat_r8"])
    assert GDI_ONLY_RESOURCE <= resource_names(["gdi_current"])


def test_the_r8_distribution_has_the_policy_and_gdi_current_does_not(generator):
    def resource_fields(profiles):
        return {f["field_name"]: f for f in generator.build_schema(profiles).schema["resource_fields"]}

    assert R8_ONLY_RESOURCE <= set(resource_fields(["healthdcat_r8"]))
    assert not R8_ONLY_RESOURCE & set(resource_fields(["gdi_current"]))
    # one policy at most (odrl:hasPolicy 0..1)
    assert "multiple_text" not in str(resource_fields(["healthdcat_r8"])["has_policy"])


def test_the_r8_data_service_has_the_properties_of_dcat_dataservice_only(generator):
    resource_fields = {f["field_name"]: f for f in generator.build_schema(["healthdcat_r8"]).schema["resource_fields"]}
    service = resource_fields["access_services"]

    assert set(subfield_names(service)) == DATA_SERVICE
    assert set(subfield_names(subfields_of(service, "publisher"))) == AGENT
    contact = subfields_of(service, "contact")
    assert set(subfield_names(contact)) == {"uri", "email", "url"}
    assert "multiple_text" not in str(subfields_of(contact, "url"))


def test_the_opening_hours_describe_a_temporal_entity(generator):
    hdab = dataset_fields(generator, ["healthdcat_r8"])["hdab"]

    for name in ("opening_hours", "special_opening_hours"):
        field = next(f for f in hdab["repeating_subfields"] if f["field_name"] == name)
        assert subfield_names(field) == ["description_translated", "frequency"]


@pytest.mark.parametrize(
    "profiles, has_subfields",
    [(["healthdcat_r8"], True), (["healthdcat_r8", "gdi_current"], True), (["gdi_current", "healthdcat_r8"], False)],
    ids=["r8", "r8 first", "gdi_current first"],
)
def test_the_pack_listed_first_decides_whether_the_contact_point_subfields_exist(generator, profiles, has_subfields):
    hdab = dataset_fields(generator, profiles)["hdab"]

    assert (set(CONTACT_POINT_SUBFIELDS) <= set(subfield_names(hdab))) is has_subfields


def test_has_structured_data_is_a_boolean_like_trusted_data_holder(generator):
    fields = dataset_fields(generator, ["gdi_current", "healthdcat_r8"])
    flag, existing = fields["has_structured_data"], fields["trusted_data_holder"]

    for key in ("preset", "validators", "output_validators"):
        assert flag[key] == existing[key]
    assert [c["value"] for c in flag["choices"]] == [c["value"] for c in existing["choices"]]


def test_has_structured_data_is_shown_as_the_xsd_boolean(generator):
    flag = dataset_fields(generator, ["healthdcat_r8"])["has_structured_data"]

    assert {c["value"]: c["label"] for c in flag["choices"]} == {False: "false", True: "true"}


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


def test_retiring_r8_prunes_the_fields_only_r8_defines_and_spares_the_shared_extras(generator):
    """related_resource and source stay: the shared RDF mapping reads and writes them as free extras."""
    retired = generator.retired_fields(["gdi_current"])

    assert set(retired["dataset_fields"]) == R8_ONLY - {"related_resource", "source"}
    assert {packs[0] for packs in retired["dataset_fields"].values()} == {"healthdcat_r8"}
    assert set(retired["resource_fields"]) == R8_ONLY_RESOURCE


def test_retiring_gdi_current_prunes_what_only_it_defines(generator):
    retired = generator.retired_fields(["healthdcat_r8"])

    assert set(retired["dataset_fields"]) == GDI_ONLY
    assert set(retired["resource_fields"]) == GDI_ONLY_RESOURCE


@pytest.mark.parametrize("profiles", [["gdi_current", "healthdcat_r8"], ["healthdcat_r8", "gdi_current"]])
def test_with_both_packs_enabled_nothing_is_retired(generator, profiles):
    assert generator.retired_fields(profiles) == {"dataset_fields": {}, "resource_fields": {}}


def test_the_r8_pack_ships_its_conformance_rules(generator):
    registry = generator.Registry()

    assert registry.pack("healthdcat_r8").conformance == "conformance/healthdcat_r8.json"
    assert registry.conformance(registry.pack("gdi_current")) is None


# --- dataset series -----------------------------------------------------------------

SERIES_R8 = {
    "title_translated", "name", "notes_translated", "applicable_legislation", "contact", "frequency",
    "spatial_coverage", "modified", "publisher", "owner_org", "issued", "temporal_coverage",
}


def series_schema(generator, reference):
    module, _, relative = reference.partition(":")
    assert module == "ckanext.gdi_userportal"
    return yaml.safe_load((generator.PACK_ROOT.parent / relative).read_text())


def series_fields(generator, profiles):
    reference = generator.build_schema(profiles).series_schema
    return {f["field_name"]: f for f in series_schema(generator, reference)["dataset_fields"]}


def test_each_pack_has_its_own_series_schema_and_the_first_pack_decides(generator):
    build = generator.build_schema

    assert build(["healthdcat_r8"]).series_schema.endswith("dataset_series_r8.yaml")
    assert build(["gdi_current"]).series_schema.endswith("dataset_series_multilingual.yaml")
    assert build(["healthdcat_r8", "gdi_current"]).series_schema.endswith("dataset_series_r8.yaml")
    assert build(["gdi_current", "healthdcat_r8"]).series_schema.endswith("dataset_series_multilingual.yaml")


def test_the_r8_series_has_the_properties_of_dcat_datasetseries_only(generator):
    fields = series_fields(generator, ["healthdcat_r8"])

    assert set(fields) == SERIES_R8
    assert set(subfield_names(fields["publisher"])) == AGENT
    assert set(subfield_names(fields["contact"])) == {"uri", "email", "url"}
    assert "multiple_text" not in str(subfields_of(fields["contact"], "url"))
    assert set(subfield_names(fields["spatial_coverage"])) == LOCATION


def test_gdi_current_keeps_the_order_fields_and_the_legacy_publisher_on_its_series(generator):
    fields = series_fields(generator, ["gdi_current"])

    assert {"series_order_field", "series_order_type"} <= set(fields)
    assert {"publisher_note", "publisher_type"} <= set(subfield_names(fields["publisher"]))


def test_a_series_schema_keeps_the_filter_metadata_the_frontend_uses(generator):
    r8 = series_fields(generator, ["healthdcat_r8"])
    gdi = series_fields(generator, ["gdi_current"])

    for name in SERIES_R8:
        assert r8[name].get("facet_key") == gdi[name].get("facet_key"), name
        assert r8[name].get("filter_help_text") == gdi[name].get("filter_help_text"), name



def is_list(subfield):
    return subfield.get("preset") == "multiple_text" or "scheming_multiple_text" in subfield.get("validators", "")


def test_r8_relationship_holds_several_relations_and_roles(generator):
    subfields = {f["field_name"]: f for f in dataset_fields(generator, ["healthdcat_r8"])["qualified_relation"]["repeating_subfields"]}

    assert set(subfields) == {"uri", "relation", "role"}
    assert is_list(subfields["relation"]) and is_list(subfields["role"])


def test_gdi_current_relationship_keeps_one_relation_and_role(generator):
    subfields = {f["field_name"]: f for f in dataset_fields(generator, ["gdi_current"])["qualified_relation"]["repeating_subfields"]}

    assert not is_list(subfields["relation"]) and not is_list(subfields["role"])


def test_r8_calls_the_spatial_resolution_by_its_r8_name_and_geographical_coverage_too(generator):
    r8 = dataset_fields(generator, ["healthdcat_r8"])
    gdi = dataset_fields(generator, ["gdi_current"])

    assert r8["spatial_resolution_in_meters"]["label"] == "Spatial resolution"
    assert gdi["spatial_resolution_in_meters"]["label"] == "Spatial resolution in meters"
    assert r8["spatial_coverage"]["label"] == "Geographical coverage"
    assert gdi["spatial_coverage"]["label"] == "Spatial coverage"
    resource = {f["field_name"]: f for f in generator.build_schema(["healthdcat_r8"]).schema["resource_fields"]}
    assert resource["spatial_resolution_in_meters"]["label"] == "Spatial resolution"


# The property names of dcat:Distribution in the R8 model, by CKAN resource field
R8_DISTRIBUTION_LABELS = {
    "name_translated": "Title",
    "description_translated": "Description",
    "access_url": "Access URL",
    "download_url": "Download URL",
    "format": "Format",
    "mimetype": "Media type",
    "compress_format": "Compression format",
    "package_format": "Packaging format",
    "size": "Byte size",
    "hash": "Checksum",
    "hash_algorithm": "Checksum algorithm",
    "rights": "Rights",
    "license": "Licence",
    "availability": "Availability",
    "status": "Status",
    "issued": "Release date",
    "modified": "Modification date",
    "has_policy": "Has policy",
    "temporal_resolution": "Temporal resolution",
    "spatial_resolution_in_meters": "Spatial resolution",
    "language": "Language",
    "documentation": "Documentation",
    "conforms_to": "Linked schemas",
    "applicable_legislation": "Applicable legislation",
}


def test_a_distribution_has_every_r8_property_under_its_r8_name(generator):
    resource = {f["field_name"]: f for f in generator.build_schema(["healthdcat_r8"]).schema["resource_fields"]}

    assert {name: resource[name]["label"] for name in R8_DISTRIBUTION_LABELS} == R8_DISTRIBUTION_LABELS
    assert "access_services" in resource


def test_gdi_current_keeps_the_names_it_always_had_for_a_distribution(generator):
    resource = {f["field_name"]: f for f in generator.build_schema(["gdi_current"]).schema["resource_fields"]}

    assert resource["name_translated"]["label"] == "Name"
    assert resource["compress_format"]["label"] == "Compress format"
    assert resource["conforms_to"]["label"] == "Conforms to"
    assert resource["size"]["label"] == "Size"


def test_r8_agents_with_a_cardinality_of_one_are_not_lists_and_the_retention_period_neither(generator):
    r8 = dataset_fields(generator, ["healthdcat_r8"])
    gdi = dataset_fields(generator, ["gdi_current"])

    for name in ("publisher", "hdab", "custodian", "hdab_coordinator", "retention_period"):
        assert r8[name].get("repeating_once") is True, name
    assert not r8["creator"].get("repeating_once"), "a dataset can have several creators"
    assert not gdi["retention_period"].get("repeating_once")


def test_r8_agent_names_are_one_or_more_names_per_language(generator):
    fields = dataset_fields(generator, ["healthdcat_r8"])

    for name in ("publisher", "creator", "hdab", "custodian", "hdab_coordinator"):
        translated = subfields_of(fields[name], "name_translated")
        assert translated["preset"] == "fluent_text", name
        assert translated["display_replaces"] == "name", name
        assert translated["display_label"] == "Name", name


def test_the_properties_of_the_contact_point_are_grouped_for_display(generator):
    fields = dataset_fields(generator, ["healthdcat_r8"])
    grouped = {"email", "url", "telephone", "opening_hours", "special_opening_hours"}

    for name in ("publisher", "hdab", "custodian", "hdab_coordinator"):
        in_group = {f["field_name"] for f in fields[name]["repeating_subfields"] if f.get("display_group") == "Contact point"}
        assert in_group == grouped, name
    assert not any(f.get("display_group") for f in fields["creator"]["repeating_subfields"])
    gdi = dataset_fields(generator, ["gdi_current"])
    assert not any(f.get("display_group") for f in gdi["publisher"]["repeating_subfields"])


def test_r8_attribution_holds_several_roles_and_gdi_current_one(generator):
    def role(profiles):
        return subfields_of(dataset_fields(generator, profiles)["qualified_attribution"], "role")

    assert is_list(role(["healthdcat_r8"]))
    assert not is_list(role(["gdi_current"]))


def test_r8_landing_page_and_type_are_lists_and_gdi_current_keeps_one_value(generator):
    r8 = dataset_fields(generator, ["healthdcat_r8"])
    gdi = dataset_fields(generator, ["gdi_current"])

    for name in ("url", "dcat_type"):
        assert is_list(r8[name]), name
        assert not is_list(gdi[name]), name
    assert r8["url"]["display_snippet"] == "link_list.html"


def test_the_opening_hours_have_a_description_per_language_and_several_frequencies(generator):
    fields = dataset_fields(generator, ["healthdcat_r8"])

    for agent in ("publisher", "hdab", "custodian", "hdab_coordinator"):
        for hours in ("opening_hours", "special_opening_hours"):
            field = subfields_of(fields[agent], hours)
            description = subfields_of(field, "description_translated")
            assert description["preset"] == "fluent_text", f"{agent}.{hours}"
            assert description["display_snippet"] == "all_languages.html", f"{agent}.{hours}"
            assert is_list(subfields_of(field, "frequency")), f"{agent}.{hours}"
