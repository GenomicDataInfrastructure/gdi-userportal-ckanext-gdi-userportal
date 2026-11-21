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
# ckanext-fluent presets that store one text per language: {"en": "...", "nl": "..."}
FLUENT_TEXT_PRESETS = {"fluent_markdown", "fluent_text"}
# the ckanext-fluent preset that stores a list of keywords per language: {"en": ["a"], "nl": ["b"]}
FLUENT_TAGS_PRESETS = {"fluent_tags"}
TRANSLATED_SUFFIX = "_translated"


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


def empty_value(field: Mapping):
    """What a field without a value looks like in the API: ``[]`` for a field that holds a list, None otherwise.

    A field with repeating subfields is a list of rows in the API also when it has one row at most
    (``repeating_once``), unlike for the indexing (``is_multiple``).
    """
    return [] if field.get("repeating_subfields") or is_multiple(field) else None


def solr_options(field: Mapping) -> dict:
    """The ``solr`` key of a field (what its Solr fields look like), an empty mapping when it has none."""
    options = field.get("solr") if isinstance(field, Mapping) else None
    return options if isinstance(options, Mapping) else {}


def canonical_prefix(field: Mapping) -> str:
    """``solr: {canonical_prefix: <uri prefix>}``: the URI prefix the indexing writes the values of the field with.

    A value that starts with the prefix in the other scheme (``https`` for an ``http`` prefix and the other way
    round) is indexed with the prefix given, so one term is one filter value. An empty text when there is none.
    """
    prefix = solr_options(field).get("canonical_prefix")
    return prefix if isinstance(prefix, str) else ""


def translated_keywords_of(field: Mapping) -> str:
    """The field a multilingual keyword field (``fluent_tags``, named ``<x>_translated``) is the translation of.

    ``tags_translated`` gives ``tags``; an empty text for any other field.
    """
    if not isinstance(field, Mapping):
        return ""
    name = str(field.get("field_name") or "")
    if str(field.get("preset", "")) in FLUENT_TAGS_PRESETS and name.endswith(TRANSLATED_SUFFIX):
        return name[: -len(TRANSLATED_SUFFIX)]
    return ""


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


def translate_options(field: Mapping) -> dict | None:
    """The ``translate`` key of a field: None when the field is not translated, otherwise its options (``{}`` for ``true``).

    ``translate: true`` shows the value of the field, or each value of a list, as ``{name, display_name}``.
    ``translate: {label_in: <sibling>}`` leaves the value as it is and writes its translation to the sibling
    field instead.
    """
    value = field.get("translate") if isinstance(field, Mapping) else None
    if isinstance(value, Mapping):
        return dict(value)
    return {} if value is True else None


def is_agent(field: Mapping) -> bool:
    """Whether the field holds agents (``agent: true``): organisations or persons that have an ``identifier`` list."""
    return isinstance(field, Mapping) and field.get("agent") is True


def _plan(fields: Iterable[Mapping], marks) -> Dict[str, dict]:
    """``{field name: node}`` of the fields that ``marks`` selects and of the fields that have such a subfield.

    A node is ``{"mark": <what marks returned>, "children": {...}}``; ``mark`` is None for a field that is only
    there for the subfields below it.
    """
    plan: Dict[str, dict] = {}
    for name, field in by_name(fields).items():
        children = _plan(subfields(field), marks)
        mark = marks(field)
        if mark is not None or children:
            plan[name] = {"mark": mark, "children": children}
    return plan


def translation_plan(fields: Iterable[Mapping]) -> Dict[str, dict]:
    """The fields the API shows as ``{name, display_name}``: ``{name: {"mark": options | None, "children": {...}}}``."""
    return _plan(fields, translate_options)


def agent_plan(fields: Iterable[Mapping]) -> Dict[str, dict]:
    """The fields that hold agents, and the fields that hold such fields: ``{name: {"mark": True | None, "children": {...}}}``."""
    return _plan(fields, lambda field: True if is_agent(field) else None)


def fluent_text_fields(*field_lists: Iterable[Mapping]) -> List[str]:
    """Names of the multilingual text fields (``fluent_markdown``, ``fluent_text``) at any depth, in any list of fields.

    A field named ``<x>_translated`` is not among them: it is the multilingual version of ``<x>`` and is read as such.
    """
    names: Dict[str, None] = {}
    for fields in field_lists:
        for path, field in walk(fields):
            name = path[-1]
            if str(field.get("preset", "")) in FLUENT_TEXT_PRESETS and not name.endswith("_translated"):
                names[name] = None
    return list(names)


def by_name(fields: Iterable[Mapping]) -> Dict[str, dict]:
    """``{field_name: field}`` of the fields that have a name."""
    return {field["field_name"]: field for field in fields or [] if isinstance(field, Mapping) and field.get("field_name")}


def walk(fields: Iterable[Mapping], path: Tuple[str, ...] = ()) -> Iterator[Tuple[Tuple[str, ...], dict]]:
    """Every field and, below it, every subfield, as ``(path of field names, field)``; a field before its subfields."""
    for name, field in by_name(fields).items():
        here = path + (name,)
        yield here, field
        yield from walk(subfields(field), here)
