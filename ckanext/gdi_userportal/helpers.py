"""Template helpers for ckanext-gdi-userportal."""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any

import ckan.plugins.toolkit as tk


def _ensure_data_dict(data: dict[str, Any] | None, package_id: str | None) -> dict[str, Any]:
    """Return a dataset dict for the current helper call.

    When a dataset dict is not provided but an id is, fetch it via the
    ``package_show`` action. Failures are ignored so the helper still returns
    a sensible default instead of aborting rendering.
    """
    if data is not None:
        return data

    if not package_id:
        return {}

    try:
        return tk.get_action("package_show")(
            {"ignore_auth": True}, {"id": package_id}
        )
    except (tk.ObjectNotFound, tk.NotAuthorized):
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
        if not value:
            return True
        return all(_is_missing_value(v) for v in value.values())

    if isinstance(value, (list, tuple, set)):
        if not value:
            return True
        return all(_is_missing_value(v) for v in value)

    return False


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

            field_name = field.get("field_name")
            if field_name:
                page_missing.append(field_name)

        missing_per_page.append(page_missing)

    return missing_per_page


def get_helpers() -> dict[str, Any]:
    return {"scheming_missing_required_fields": scheming_missing_required_fields}
