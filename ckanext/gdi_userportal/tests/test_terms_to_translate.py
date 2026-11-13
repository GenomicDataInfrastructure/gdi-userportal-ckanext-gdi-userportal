# SPDX-FileCopyrightText: 2026 Stichting Health-RI
#
# SPDX-License-Identifier: Apache-2.0

from copy import deepcopy
from unittest.mock import patch

import pytest
from ckan.plugins import toolkit

from ckanext.gdi_userportal.logic.action.get import gdi_terms_to_translate
from ckanext.gdi_userportal.logic.auth import get as auth
from ckanext.gdi_userportal.plugin import GdiUserPortalPlugin

SCHEMA = {
    "dataset_fields": [
        {"field_name": "colour", "translate": True},
        {"field_name": "shape"},
        {
            "field_name": "activity",
            "repeating_subfields": [{"field_name": "kind", "translate": True}, {"field_name": "note"}],
        },
    ],
    "resource_fields": [{"field_name": "format", "translate": True}],
    "form_languages": ["en", "nl"],
}


def _terms(package):
    with patch("ckanext.gdi_userportal.schema_access.dataset_schema", return_value=SCHEMA), patch.object(
        toolkit, "check_access"
    ):
        return gdi_terms_to_translate({}, {"package": package})


def test_the_terms_are_the_values_of_the_fields_the_schema_marks_translate():
    package = {
        "colour": ["http://example.org/red", "http://example.org/blue"],
        "shape": "http://example.org/round",
        "activity": [{"kind": "http://example.org/kind", "note": "http://example.org/note"}],
        "resources": [{"format": "http://example.org/csv", "name": "http://example.org/name"}],
    }

    assert _terms(package) == {
        "terms": [
            "http://example.org/blue",
            "http://example.org/csv",
            "http://example.org/kind",
            "http://example.org/red",
        ]
    }


def test_the_terms_are_sorted_and_without_doubles():
    package = {"colour": ["b", "a", "b"], "resources": [{"format": "a"}]}

    assert _terms(package) == {"terms": ["a", "b"]}


def test_the_dataset_is_not_changed():
    package = {"colour": "red", "resources": [{"format": "csv"}]}
    before = deepcopy(package)

    _terms(package)

    assert package == before


@pytest.mark.parametrize("resources", [None, [], [None, "text"]])
def test_resources_that_are_missing_or_not_objects_are_skipped(resources):
    assert _terms({"colour": "red", "resources": resources}) == {"terms": ["red"]}


def test_a_dataset_without_resources_key_has_terms_too():
    assert _terms({"colour": "red"}) == {"terms": ["red"]}


@pytest.mark.parametrize("data_dict", [{}, {"package": None}, {"package": "text"}, {"package": ["a"]}])
def test_the_package_is_required(data_dict):
    with patch.object(toolkit, "check_access"):
        with pytest.raises(toolkit.ValidationError):
            gdi_terms_to_translate({}, data_dict)


def test_the_action_and_its_authorisation_are_registered():
    plugin = GdiUserPortalPlugin()

    assert plugin.get_actions()["gdi_terms_to_translate"] is gdi_terms_to_translate
    assert plugin.get_auth_functions()["gdi_terms_to_translate"] is auth.gdi_terms_to_translate


def test_only_sysadmins_pass_the_authorisation():
    with patch.object(toolkit, "_", side_effect=lambda text: text):
        assert auth.gdi_terms_to_translate({"user": "someone"}, {})["success"] is False
