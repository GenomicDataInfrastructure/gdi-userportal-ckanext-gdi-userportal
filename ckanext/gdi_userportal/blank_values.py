# SPDX-FileCopyrightText: 2026 Stichting Health-RI
#
# SPDX-License-Identifier: Apache-2.0

"""
Values that hold nothing, and the dataset without them.

The edit form posts an input for every language and every subfield, and the RDF profiles fill every form
language with an empty text, so a dataset is stored with ``{"en": "", "nl": ""}``, ``[]`` and ``""``
as extras unless they are removed. Those rows say nothing and take space in the database and in every API answer; the code that
reads a dataset has to cope with a field that is not there anyway (a dataset that never had it).

Standard library only. ``0`` and ``False`` are values, not blanks.
"""

import json
from typing import Any, Collection, Iterable, Mapping, Optional


def _blank(value: Any) -> bool:
    """Whether a value holds nothing at any depth: no text, no item, no language."""
    if value is None:
        return True
    if isinstance(value, str):
        stripped = value.strip()
        if not stripped:
            return True
        if stripped[0] in "[{":
            try:
                parsed = json.loads(stripped)
            except ValueError:
                return False
            return isinstance(parsed, (list, dict)) and _blank(parsed)
        return False
    if isinstance(value, Mapping):
        return all(_blank(item) for item in value.values())
    if isinstance(value, (list, tuple)):
        return all(_blank(item) for item in value)
    return False


def _flat(value: Any) -> bool:
    """A text per language, or a list of texts: no row, no list of rows inside."""
    if isinstance(value, Mapping):
        return all(_flat(item) for item in value.values())
    if isinstance(value, (list, tuple)):
        return not any(isinstance(item, (Mapping, list, tuple)) for item in value)
    return True


def _tidy(value: Any) -> Any:
    """The value without the empty items of a flat list and the empty entries of a flat map.

    Only that: a row of a repeating field is never changed from the inside (``{"role": "", "agent": [...]}``
    keeps its ``role``), because the validation of the nested subfields is not written for a row that lacks a
    key it had. A flat map is a text per language (``{"en": "Title", "nl": ""}``) or a list of texts per
    language, a flat list a list of texts.
    """
    if not _flat(value):
        return value
    if isinstance(value, Mapping):
        return {key: _tidy(item) for key, item in value.items() if not _blank(item)}
    if isinstance(value, (list, tuple)):
        return [item for item in value if not _blank(item)]
    return value


def prune(value: Any) -> Optional[Any]:
    """The value without its empty parts, or None when nothing is left.

    A text with only white space, an empty list or object, an object with an empty text per language, a list
    of rows that are all empty and a JSON text of any of those are empty. What stays loses the empty languages
    of a map and the empty items of a list of texts: ``{"en": "Title", "nl": ""}`` becomes ``{"en": "Title"}``
    (``_tidy`` says what is left alone). A JSON text that stays is given back as it came when nothing was left
    out of it.
    """
    if _blank(value):
        return None
    if isinstance(value, str):
        stripped = value.strip()
        if stripped[:1] in ("[", "{"):
            try:
                parsed = json.loads(stripped)
            except ValueError:
                return value
            tidied = _tidy(parsed)
            return value if tidied == parsed else json.dumps(tidied)
        return value
    return _tidy(value)


def is_blank(value: Any) -> bool:
    return prune(value) is None


def _prune_record(record: Mapping, fields: Iterable[Mapping], core: Collection[str]) -> dict:
    """The record without the fields of the schema that hold nothing; core fields and other keys stay."""
    names = {field.get("field_name") for field in fields or [] if isinstance(field, Mapping)} - set(core)
    cleaned = {}
    for key, value in record.items():
        if key not in names:
            cleaned[key] = value
            continue
        pruned = prune(value)
        if pruned is not None:
            cleaned[key] = pruned
    return cleaned


def prune_dataset(
    data_dict: Mapping,
    dataset_fields: Iterable[Mapping],
    resource_fields: Iterable[Mapping],
    core_dataset: Collection[str],
    core_resource: Collection[str],
) -> dict:
    """A copy of the dataset without the schema fields (and the resource fields) that hold nothing.

    ``core_dataset`` and ``core_resource`` name the fields CKAN keeps in a column of their own: they are
    left as they are, only the fields that end up as extras are dropped.
    """
    cleaned = _prune_record(data_dict, dataset_fields, core_dataset)
    resources = data_dict.get("resources")
    if isinstance(resources, (list, tuple)):
        cleaned["resources"] = [
            _prune_record(resource, resource_fields, core_resource) if isinstance(resource, Mapping) else resource
            for resource in resources
        ]
    return cleaned
