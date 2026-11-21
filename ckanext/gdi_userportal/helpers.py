# SPDX-FileCopyrightText: 2024 PNED G.I.E.
# SPDX-FileContributor: Stichting Health-RI
#
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

from collections.abc import Iterable
from typing import Any

import ckan.plugins.toolkit as tk

from ckanext.gdi_userportal import conformance_service


def _ensure_data_dict(data: dict[str, Any] | None, package_id: str | None) -> dict[str, Any]:
    """Return a dataset dict for the current helper call.

    When a dataset dict is not provided but an id is, fetch it via the
    ``package_show`` action. Failures are ignored so the helper still returns
    a sensible default instead of aborting rendering.
    """
    if data is not None:
        return data

    if package_id:
        try:
            return tk.get_action("package_show")(
                {"ignore_auth": True}, {"id": package_id}
            )
        except (tk.ObjectNotFound, tk.NotAuthorized):
            pass

    return {}


def _value_from_extras(data_dict: dict[str, Any], field_name: str) -> Any:
    extras = data_dict.get("extras")
    if isinstance(extras, dict):
        return extras.get(field_name)
    if isinstance(extras, Iterable):
        for extra in extras:
            if not isinstance(extra, dict):
                continue
            if extra.get("key") == field_name:
                return extra.get("value")
    return None


def _extract_field_value(field: dict[str, Any], data_dict: dict[str, Any]) -> Any:
    field_name = field.get("field_name")
    if not field_name or not data_dict:
        return None

    if field_name in data_dict:
        return data_dict[field_name]

    return _value_from_extras(data_dict, field_name)


def _is_missing_value(value: Any) -> bool:
    if value is None:
        return True

    if isinstance(value, str):
        return value.strip() == ""

    if isinstance(value, dict):
        return not value or all(_is_missing_value(v) for v in value.values())

    if isinstance(value, (list, tuple, set)):
        return not value or all(_is_missing_value(v) for v in value)

    return False


def is_redundant_translation(field_name: str, entry: dict[str, Any] | None) -> bool:
    """Whether ``<name>_translated`` only repeats the plain ``<name>`` of the same entry.

    The display shows both for a language map; with one language that equals the plain value
    the second row says nothing new.
    """
    suffix = "_translated"
    if not isinstance(entry, dict) or not field_name.endswith(suffix):
        return False

    translated = entry.get(field_name)
    plain = entry.get(field_name[: -len(suffix)])
    if not isinstance(translated, dict) or not isinstance(plain, str) or not plain.strip():
        return False

    texts = {v.strip() for v in translated.values() if isinstance(v, str) and v.strip()}
    return texts <= {plain.strip()}


def scheming_missing_required_fields(
    pages: list[dict[str, Any]],
    data: dict[str, Any] | None = None,
    package_id: str | None = None,
) -> list[list[str]]:
    """Return a list of missing required fields grouped per form page.

    This helper acts as the base implementation expected by
    ``ckanext-fluent``.  It mirrors the behaviour from the forked
    ckanext-scheming version previously used in this project and makes sure
    chained helpers can extend the result again.
    """
    data_dict = _ensure_data_dict(data, package_id)

    missing_per_page: list[list[str]] = []

    for page in pages or []:
        page_missing: list[str] = []
        for field in page.get("fields", []):
            # Ignore non-required fields early.
            if not tk.h.scheming_field_required(field):
                continue

            value = _extract_field_value(field, data_dict)

            # Repeating subfields can contain a list of child values; treat the
            # field as present when at least one entry contains data.
            if field.get("repeating_subfields") and isinstance(value, list):
                if any(not _is_missing_value(item) for item in value):
                    continue
            elif not _is_missing_value(value):
                continue

            if field_name := field.get("field_name"):
                page_missing.append(field_name)

        missing_per_page.append(page_missing)

    return missing_per_page


SHOW_EMPTY_PROPERTIES = "ckanext.gdi_userportal.show_empty_properties"


def show_empty_properties() -> bool:
    """Whether the display templates also list the properties that have no value.

    Off by default: a page lists what the dataset holds. Switched on, every property the schema
    defines gets a row, with a dash when it is empty, to see what the schema, the form and the
    harvest can hold.
    """
    return tk.asbool(tk.config.get(SHOW_EMPTY_PROPERTIES, False))


_SOURCE_PROFILES_CACHE = "_gdi_source_profiles"


def _source_profiles(source_ids) -> dict[str, str | None]:
    """``{harvest source id: metadata_profile or None}`` for the sources that exist.

    A page asks once per dataset or distribution it shows, so the answers are kept for the request.
    """
    from flask import g, has_app_context
    from ckan import model
    from ckanext.gdi_userportal import profile_visibility

    ids = {source_id for source_id in source_ids if source_id}
    cache = g.setdefault(_SOURCE_PROFILES_CACHE, {}) if has_app_context() else {}
    unknown = ids - cache.keys()
    if unknown:
        found = profile_visibility.source_profiles(model.Session, unknown)
        cache.update({source_id: (source_id in found, found.get(source_id)) for source_id in unknown})
    return {source_id: cache[source_id][1] for source_id in ids if cache[source_id][0]}


def profile_conformance(record: dict[str, Any] | None) -> dict[str, Any] | None:
    """The conformance of a dataset or dataset series to the metadata profiles it comes from.

    For the dataset, series and search pages; see ``conformance_service.page_indicator``. None when there is
    nothing to show; never raises.
    """
    return conformance_service.page_indicator(record, tk.config, _source_profiles)


def resource_conformance(dataset: dict[str, Any] | None, resource: dict[str, Any] | None) -> dict[str, Any] | None:
    """The same for one distribution of ``dataset``, labelled sample or analytics where it is one.

    See ``conformance_service.resource_indicator``. None when there is nothing to show; never raises.
    """
    return conformance_service.resource_indicator(dataset, resource, tk.config, _source_profiles)


def empty_property_scope(record: dict[str, Any] | None, section: str) -> frozenset[str] | None:
    """The fields of ``section`` (``dataset_fields`` or ``resource_fields``) a page lists as empty for ``record``.

    Only used when ``show_empty_properties`` is on. None means every field of the schema; see
    ``conformance_service.empty_property_scope``. Never raises.
    """
    return conformance_service.empty_property_scope(record, section, tk.config, _source_profiles)


def get_helpers() -> dict[str, Any]:
    return {
        "gdi_empty_property_scope": empty_property_scope,
        "gdi_profile_conformance": profile_conformance,
        "gdi_resource_conformance": resource_conformance,
        "scheming_missing_required_fields": scheming_missing_required_fields,
        "gdi_show_empty_properties": show_empty_properties,
        "gdi_is_blank_value": _is_missing_value,
        "gdi_is_redundant_translation": is_redundant_translation,
    }
