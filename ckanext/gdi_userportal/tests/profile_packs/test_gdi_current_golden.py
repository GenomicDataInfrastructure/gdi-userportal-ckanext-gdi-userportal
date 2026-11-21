# SPDX-FileCopyrightText: 2026 Stichting Health-RI
#
# SPDX-License-Identifier: Apache-2.0

"""
Acceptance test for ADR 0001: with only ``gdi_current`` enabled, the generated
dataset schema is the schema the stack loaded before the generator existed.

``scheming/schemas/dataset_multilingual.yaml`` is that baseline. It stays in the
tree unchanged, and this test fails when it and the ``gdi_current`` pack drift apart.
"""

import yaml
from conftest import STATIC_DATASET_SCHEMA


def _baseline():
    return yaml.safe_load(STATIC_DATASET_SCHEMA.read_text(encoding="utf-8"))


def _names(fields):
    return [field["field_name"] for field in fields]


def test_dataset_fields_keep_the_form_order(generator):
    generated = generator.build_schema(["gdi_current"]).schema

    assert _names(generated["dataset_fields"]) == _names(_baseline()["dataset_fields"])


def test_resource_fields_keep_the_form_order(generator):
    generated = generator.build_schema(["gdi_current"]).schema

    assert _names(generated["resource_fields"]) == _names(_baseline()["resource_fields"])


def test_every_field_is_identical(generator):
    generated = generator.build_schema(["gdi_current"]).schema
    baseline = _baseline()

    for section in ("dataset_fields", "resource_fields"):
        for got, want in zip(generated[section], baseline[section]):
            assert got == want, f"{section}.{want['field_name']} differs"


def test_generated_schema_equals_the_static_schema(generator):
    generated = generator.build_schema(["gdi_current"]).schema

    assert generated == _baseline()


def test_the_rendered_yaml_loads_back_to_the_static_schema(generator):
    rendered = generator.render_schema(generator.build_schema(["gdi_current"]).schema)

    assert yaml.safe_load(rendered) == _baseline()


def test_rendered_yaml_has_no_anchors(generator):
    """Scheming reads the file with a plain loader; aliases would be fragile."""
    rendered = generator.render_schema(generator.build_schema(["gdi_current"]).schema)

    assert " &id" not in rendered and " *id" not in rendered
