# SPDX-FileCopyrightText: 2026 Stichting Health-RI
#
# SPDX-License-Identifier: Apache-2.0

"""
The helpers the display templates use to leave out what has nothing to show.

They are plain functions, so this runs on the host with only pytest, without CKAN (the import
of the toolkit is stubbed):

    uv run --no-project --with pytest python -I -m pytest \
        ckanext/gdi_userportal/tests/test_display_helpers.py
"""

import importlib.util
import sys
import types
from pathlib import Path

import pytest

HELPERS = Path(__file__).resolve().parents[1] / "helpers.py"


@pytest.fixture(scope="module")
def helpers():
    stubs = {}
    for name in ("ckan", "ckan.plugins", "ckan.plugins.toolkit"):
        stubs[name] = types.ModuleType(name)
    stubs["ckan"].plugins = stubs["ckan.plugins"]
    stubs["ckan.plugins"].toolkit = stubs["ckan.plugins.toolkit"]
    saved = {name: sys.modules.get(name) for name in stubs}
    sys.modules.update(stubs)
    try:
        spec = importlib.util.spec_from_file_location("gdi_display_helpers", HELPERS)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        yield module
    finally:
        for name, original in saved.items():
            if original is None:
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = original


@pytest.mark.parametrize(
    "value",
    [None, "", "  ", [], {}, [""], [{}], {"en": "", "nl": ""}, [{"start": "", "end": None}], {"en": [], "nl": ""}],
)
def test_a_value_without_text_is_blank(helpers, value):
    assert helpers.get_helpers()["gdi_is_blank_value"](value) is True


@pytest.mark.parametrize(
    "value",
    ["text", 0, False, ["a"], {"en": "", "nl": "tekst"}, [{"uri": "http://example.org"}], [{"start": "", "end": "2024"}]],
)
def test_a_value_with_something_in_it_is_not_blank(helpers, value):
    assert helpers.get_helpers()["gdi_is_blank_value"](value) is False


def test_a_translation_equal_to_the_plain_value_is_redundant(helpers):
    entry = {"name": "Registry", "name_translated": {"en": "Registry", "nl": ""}}

    assert helpers.is_redundant_translation("name_translated", entry) is True


def test_a_translation_with_another_text_is_not_redundant(helpers):
    entry = {"name": "Registry", "name_translated": {"en": "Registry", "nl": "Register"}}

    assert helpers.is_redundant_translation("name_translated", entry) is False


@pytest.mark.parametrize(
    "field_name, entry",
    [
        ("name", {"name": "Registry"}),
        ("name_translated", {"name_translated": {"en": "Registry"}}),
        ("name_translated", {"name": "", "name_translated": {"en": "Registry"}}),
        ("name_translated", {"name": "Registry", "name_translated": "Registry"}),
        ("name_translated", None),
    ],
    ids=["not a translation", "no plain value", "blank plain value", "not a language map", "no entry"],
)
def test_without_a_plain_value_to_repeat_nothing_is_redundant(helpers, field_name, entry):
    assert helpers.is_redundant_translation(field_name, entry) is False
