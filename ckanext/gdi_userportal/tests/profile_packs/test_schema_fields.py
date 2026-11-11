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
