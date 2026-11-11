# SPDX-FileCopyrightText: 2026 Stichting Health-RI
#
# SPDX-License-Identifier: Apache-2.0

"""Reading the generated dataset schema (profile_packs/schema_fields.py)."""

import sys

from conftest import PACKAGE_DIR

sys.path.insert(0, str(PACKAGE_DIR.parents[1]))

from ckanext.gdi_userportal.profile_packs import schema_fields as fields  # noqa: E402


def field(name, **attributes):
    return {"field_name": name, **attributes}


def test_subfields_are_the_repeating_subfields():
    parent = field("a", repeating_subfields=[field("b"), field("c")])

    assert [subfield["field_name"] for subfield in fields.subfields(parent)] == ["b", "c"]


def test_a_field_without_subfields_has_none():
    assert fields.subfields(field("a")) == []
    assert fields.subfields(field("a", repeating_subfields=None)) == []
    assert fields.subfields(None) == []


def test_by_name_skips_what_has_no_name():
    named = fields.by_name([field("a"), {"label": "no name"}, "not a field", field("b")])

    assert list(named) == ["a", "b"]


def test_walk_lists_a_field_before_its_subfields_with_the_path_to_it():
    schema = [
        field("a", repeating_subfields=[field("b", repeating_subfields=[field("c")]), field("d")]),
        field("e"),
    ]

    assert [path for path, _ in fields.walk(schema)] == [("a",), ("a", "b"), ("a", "b", "c"), ("a", "d"), ("e",)]


def test_walk_yields_the_field_itself():
    leaf = field("c", preset="select")

    assert dict(fields.walk([field("a", repeating_subfields=[leaf])]))[("a", "c")] is leaf


def test_walk_accepts_nothing():
    assert list(fields.walk(None)) == []


def test_translate_true_has_no_options_and_a_mapping_has_them():
    assert fields.translate_options(field("a", translate=True)) == {}
    assert fields.translate_options(field("a", translate={"label_in": "label"})) == {"label_in": "label"}


def test_a_field_that_is_not_marked_is_not_translated():
    assert fields.translate_options(field("a")) is None
    assert fields.translate_options(field("a", translate=False)) is None
    assert fields.translate_options(None) is None


def test_the_translation_plan_holds_the_marked_fields_and_the_fields_with_a_marked_subfield():
    schema = [
        field("theme", translate=True),
        field("title"),
        field("publisher", repeating_subfields=[field("name"), field("type", translate=True)]),
        field("contact", repeating_subfields=[field("name"), field("email")]),
        field(
            "activity",
            repeating_subfields=[field("agent", repeating_subfields=[field("type", translate=True)]), field("label")],
        ),
    ]

    plan = fields.translation_plan(schema)

    assert list(plan) == ["theme", "publisher", "activity"]
    assert plan["theme"] == {"mark": {}, "children": {}}
    assert plan["publisher"]["mark"] is None
    assert list(plan["publisher"]["children"]) == ["type"]
    assert list(plan["activity"]["children"]["agent"]["children"]) == ["type"]


def test_the_translation_plan_keeps_the_options_of_a_mark():
    plan = fields.translation_plan(
        [field("activity", repeating_subfields=[field("dct_type", translate={"label_in": "label"})])]
    )

    assert plan["activity"]["children"]["dct_type"]["mark"] == {"label_in": "label"}


def test_the_agent_plan_holds_the_agents_and_the_fields_that_hold_agents():
    schema = [
        field("publisher", agent=True, repeating_subfields=[field("name")]),
        field("custodian", repeating_subfields=[field("name")]),
        field(
            "activity",
            repeating_subfields=[field("associated", agent=True, repeating_subfields=[field("behalf_of", agent=True)])],
        ),
    ]

    plan = fields.agent_plan(schema)

    assert list(plan) == ["publisher", "activity"]
    assert plan["publisher"]["mark"] is True
    assert plan["activity"]["mark"] is None
    assert plan["activity"]["children"]["associated"]["children"]["behalf_of"]["mark"] is True


def test_the_fluent_text_fields_are_found_at_any_depth_and_the_translated_ones_are_left_out():
    schema = [
        field("provenance", preset="fluent_markdown"),
        field("title_translated", preset="fluent_text"),
        field("publisher", repeating_subfields=[field("publisher_note", preset="fluent_markdown")]),
        field("notes", preset="markdown"),
    ]

    assert fields.fluent_text_fields(schema, [field("rights", preset="fluent_markdown")]) == [
        "provenance",
        "publisher_note",
        "rights",
    ]
