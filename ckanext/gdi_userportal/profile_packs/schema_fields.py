# SPDX-FileCopyrightText: 2026 Stichting Health-RI
#
# SPDX-License-Identifier: Apache-2.0

"""
Reading the generated dataset schema: which fields hold lists, which subfields a field has.

The Solr schema sync, the indexing and the translation of the API all ask the same questions of the
schema, so they ask them here and none of them keeps a list of field names of its own. What a field
says about its Solr fields and about its translation (the ``solr`` and ``translate`` keys) is read
through this module too; ``README.md`` describes the keys.

It runs from the container start scripts through ``solr_schema`` and imports nothing but the
standard library.
"""

from __future__ import annotations

from typing import Dict, Iterable, Iterator, List, Mapping, Tuple

# dataset_series_in_series and series_validator: ckanext-dataset-series keeps in_series as a list of series ids
MULTIPLE_PRESETS = {"multiple_text", "multiple_select", "multiple_checkbox", "dataset_series_in_series"}
MULTIPLE_VALIDATORS = {"scheming_multiple_choice", "scheming_multiple_text", "series_validator"}


def subfields(field: Mapping) -> List[dict]:
    """The repeating subfields of a scheming field, none for a field without them."""
    value = field.get("repeating_subfields") if isinstance(field, Mapping) else None
    return [subfield for subfield in value if isinstance(subfield, Mapping)] if isinstance(value, list) else []


def is_multiple(field: Mapping) -> bool:
    """Whether a scheming field holds a list: repeating subfields (more than one), multiple text or choice."""
    if field.get("repeating_subfields"):
        return not field.get("repeating_once")
    if field.get("preset") in MULTIPLE_PRESETS:
        return True
    return bool(MULTIPLE_VALIDATORS & set(str(field.get("validators", "")).split()))


def by_name(fields: Iterable[Mapping]) -> Dict[str, dict]:
    """``{field_name: field}`` of the fields that have a name."""
    return {field["field_name"]: field for field in fields or [] if isinstance(field, Mapping) and field.get("field_name")}


def walk(fields: Iterable[Mapping], path: Tuple[str, ...] = ()) -> Iterator[Tuple[Tuple[str, ...], dict]]:
    """Every field and, below it, every subfield, as ``(path of field names, field)``; a field before its subfields."""
    for name, field in by_name(fields).items():
        here = path + (name,)
        yield here, field
        yield from walk(subfields(field), here)
