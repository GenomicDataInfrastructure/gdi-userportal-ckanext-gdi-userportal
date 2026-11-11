# SPDX-FileCopyrightText: 2026 Stichting Health-RI
#
# SPDX-License-Identifier: Apache-2.0

"""
Acceptance test for ADR 0001: with only ``gdi_current`` enabled, the generated
dataset schema is the schema the stack loaded before the generator existed.

``scheming/schemas/dataset_multilingual.yaml`` is that baseline. It stays in the
tree unchanged, and this test fails when it and the ``gdi_current`` pack drift apart, except for
the changes listed in ``DELIBERATE_CHANGES``.

The baseline keeps the order of the form as it was; ``gdi_current`` now orders its fields
alphabetically (``field_order``), so the tests compare the same fields, each identical, by
name and not by position.
"""

import copy

import yaml
from conftest import STATIC_DATASET_SCHEMA


def _baseline():
    schema = yaml.safe_load(STATIC_DATASET_SCHEMA.read_text(encoding="utf-8"))
    for (section, name), changes in DELIBERATE_CHANGES.items():
        for field in schema[section]:
            if field["field_name"] == name:
                field.update(changes)
    for section in ("dataset_fields", "resource_fields"):
        _group_contact_points(schema[section])
    return schema


# The agents (publisher, creator, health data access body, the agent of an attribution, and those of a data
# service) show their email and URL together under the contact point, as the agents of R8 do: display_group.
# It is read by the display template only. The contact point field itself stays flat.
AGENT_FIELDS = ("publisher", "creator", "hdab", "agent")
CONTACT_POINT_SUBFIELDS = ("email", "url")


def _group_contact_points(fields):
    for field in fields:
        subfields = field.get("repeating_subfields") or []
        if field["field_name"] in AGENT_FIELDS:
            for subfield in subfields:
                if subfield["field_name"] in CONTACT_POINT_SUBFIELDS:
                    subfield["display_group"] = "Contact point"
        _group_contact_points(subfields)


def _names(fields):
    return [field["field_name"] for field in fields]


def _without_indexing_keys(value):
    """The schema without the ``solr`` key of its fields.

    The key says what the indexing writes to Solr (see ``indexing.py``); it was added after the baseline and the
    form and the display do not read it. ``test_solr_schema.py`` checks it.
    """
    if isinstance(value, dict):
        return {key: _without_indexing_keys(item) for key, item in value.items() if key != "solr"}
    if isinstance(value, list):
        return [_without_indexing_keys(item) for item in value]
    return value


# What gdi_current changed on purpose since the baseline: a dataset that is in no series stores nothing
# (scheming_multiple_choice stored the empty list "[]" in package_extra).
DELIBERATE_CHANGES = {
    ("dataset_fields", "in_series"): {"validators": "ignore_empty scheming_multiple_choice series_validator"},
}


def _by_name(fields):
    return {field["field_name"]: field for field in fields}


def _in_baseline_order(schema):
    """The schema with its fields, and the data service subfields, sorted by name, so that only the content is compared."""
    schema = copy.deepcopy(schema)
    for section in ("dataset_fields", "resource_fields"):
        schema[section] = sorted(schema[section], key=lambda field: field["field_name"])
        for field in schema[section]:
            if field["field_name"] == "access_services":
                field["repeating_subfields"] = sorted(field["repeating_subfields"], key=lambda f: f["field_name"])
    return schema


def test_the_fields_are_the_fields_of_the_baseline(generator):
    generated = generator.build_schema(["gdi_current"]).schema
    baseline = _baseline()

    for section in ("dataset_fields", "resource_fields"):
        assert sorted(_names(generated[section])) == sorted(_names(baseline[section]))


def test_every_field_is_identical(generator):
    generated = _without_indexing_keys(generator.build_schema(["gdi_current"]).schema)
    baseline = _baseline()

    for section in ("dataset_fields", "resource_fields"):
        got = _by_name(generated[section])
        for want in baseline[section]:
            if want["field_name"] == "access_services":
                continue  # its subfields are compared below, by name
            assert got[want["field_name"]] == want, f"{section}.{want['field_name']} differs"


def test_the_data_service_has_the_subfields_of_the_baseline(generator):
    generated = _by_name(generator.build_schema(["gdi_current"]).schema["resource_fields"])["access_services"]
    baseline = _by_name(_baseline()["resource_fields"])["access_services"]

    assert {k: v for k, v in generated.items() if k != "repeating_subfields"} == {
        k: v for k, v in baseline.items() if k != "repeating_subfields"
    }
    assert _by_name(generated["repeating_subfields"]) == _by_name(baseline["repeating_subfields"])


def test_generated_schema_equals_the_static_schema(generator):
    generated = _without_indexing_keys(generator.build_schema(["gdi_current"]).schema)

    assert _in_baseline_order(generated) == _in_baseline_order(_baseline())


def test_the_rendered_yaml_loads_back_to_the_generated_schema(generator):
    schema = generator.build_schema(["gdi_current"]).schema
    rendered = generator.render_schema(schema)

    assert yaml.safe_load(rendered) == schema
    assert _in_baseline_order(_without_indexing_keys(yaml.safe_load(rendered))) == _in_baseline_order(_baseline())


def test_rendered_yaml_has_no_anchors(generator):
    """Scheming reads the file with a plain loader; aliases would be fragile."""
    rendered = generator.render_schema(generator.build_schema(["gdi_current"]).schema)

    assert " &id" not in rendered and " *id" not in rendered
