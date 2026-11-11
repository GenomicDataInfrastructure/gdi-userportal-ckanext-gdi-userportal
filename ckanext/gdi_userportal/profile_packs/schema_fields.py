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


def solr_options(field: Mapping) -> dict:
    """The ``solr`` key of a field (what its Solr fields look like), an empty mapping when it has none."""
    options = field.get("solr") if isinstance(field, Mapping) else None
    return options if isinstance(options, Mapping) else {}


def flatten_paths(field: Mapping) -> List[Tuple[str, ...]]:
    """The subfields of a repeating field that get a Solr field of their own: ``solr: {flatten: [name, agent.name]}``.

    A path with a dot reaches into a subfield that has subfields itself.
    """
    flatten = solr_options(field).get("flatten")
    if isinstance(flatten, str):
        flatten = [flatten]
    if not isinstance(flatten, (list, tuple)):
        return []
    return [tuple(str(path).split(".")) for path in flatten if path]


def flatten_prefix(field: Mapping) -> str:
    """The start of the Solr field names of a flattened field: its own name unless ``solr: {prefix: ...}`` says so."""
    return str(solr_options(field).get("prefix") or field.get("field_name") or "")


def flattened_solr_fields(fields: Iterable[Mapping]) -> List[str]:
    """The Solr fields the indexing fills from the dataset fields: ``<prefix>_<subfield path joined by _>``."""
    return [
        "%s_%s" % (flatten_prefix(field), "_".join(path))
        for field in fields or []
        if isinstance(field, Mapping)
        for path in flatten_paths(field)
    ]


def by_name(fields: Iterable[Mapping]) -> Dict[str, dict]:
    """``{field_name: field}`` of the fields that have a name."""
    return {field["field_name"]: field for field in fields or [] if isinstance(field, Mapping) and field.get("field_name")}


def walk(fields: Iterable[Mapping], path: Tuple[str, ...] = ()) -> Iterator[Tuple[Tuple[str, ...], dict]]:
    """Every field and, below it, every subfield, as ``(path of field names, field)``; a field before its subfields."""
    for name, field in by_name(fields).items():
        here = path + (name,)
        yield here, field
        yield from walk(subfields(field), here)
