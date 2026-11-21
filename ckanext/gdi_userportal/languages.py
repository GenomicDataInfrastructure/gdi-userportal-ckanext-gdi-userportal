# SPDX-FileCopyrightText: 2026 Stichting Health-RI
#
# SPDX-License-Identifier: Apache-2.0

"""Language fallback for multilingual (ckanext-fluent) values.

A dataset saved from the edit form holds a value for every form language, an empty one for the
languages left blank (``{"en": "Title", "nl": ""}``). Scheming's ``scheming_language_text`` and
CKAN's ``get_translated`` only fall back to another language when the key is missing, so a page in
Dutch would show nothing for the title. Dropping the empty languages from what ``package_show``
returns lets every template and helper fall back as they do for a language that was never filled
in. The stored value is not changed.
"""

from __future__ import annotations

from typing import Any, Mapping

_CORE_SUFFIX = "_translated"


def _is_fluent(field: Mapping[str, Any]) -> bool:
    return "fluent" in str(field.get("validators", "")) or str(
        field.get("preset", "")
    ).startswith("fluent")


def _is_empty(text: Any) -> bool:
    if isinstance(text, str):
        return not text.strip()
    return text in (None, [], {})


def without_empty_languages(value: Any) -> Any:
    """The language map without the languages that hold nothing.

    A map where every language is empty is returned as it is, so the field stays a map.
    """
    if not isinstance(value, dict):
        return value
    kept = {lang: text for lang, text in value.items() if not _is_empty(text)}
    return kept or value


def _first_available(value: Mapping[str, Any]) -> Any:
    for lang in sorted(value):
        if not _is_empty(value[lang]):
            return value[lang]
    return None


def _fall_back_in(item: dict, fields: Any) -> None:
    for field in fields or []:
        if not isinstance(field, Mapping):
            continue
        name = field.get("field_name")
        value = item.get(name)

        if _is_fluent(field) and isinstance(value, dict):
            item[name] = without_empty_languages(value)
            core = name[: -len(_CORE_SUFFIX)] if name.endswith(_CORE_SUFFIX) else None
            # The core field (title, notes) is the default language's text; with that language
            # empty, fall back to what exists so a page without a matching language is not blank.
            if core and core in item and _is_empty(item[core]):
                fallback = _first_available(value)
                if isinstance(fallback, str):
                    item[core] = fallback
        elif isinstance(value, list) and field.get("repeating_subfields"):
            for row in value:
                if isinstance(row, dict):
                    _fall_back_in(row, field["repeating_subfields"])


def fall_back_to_available_languages(
    data_dict: dict, schema: Mapping[str, Any] | None
) -> dict:
    """Drop the empty languages of the fluent fields of a dataset and its resources, in place."""
    if not isinstance(schema, Mapping):
        return data_dict
    _fall_back_in(data_dict, schema.get("dataset_fields"))
    resource_fields = schema.get("resource_fields")
    for resource in data_dict.get("resources") or []:
        if isinstance(resource, dict):
            _fall_back_in(resource, resource_fields)
    return data_dict
