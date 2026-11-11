# SPDX-FileCopyrightText: 2026 Stichting Health-RI
#
# SPDX-License-Identifier: Apache-2.0

"""
The part of ``before_dataset_index`` that follows the generated dataset schema.

CKAN hands the indexer a dataset whose list fields are JSON text (``'["a", "b"]'``) and whose repeating
fields are lists of objects, which scheming turns into one ``extras_<field>__<subfield>`` text field each
once this plugin has run. Solr can neither filter nor facet on those, so the plugin writes plain
multi valued Solr fields of its own. Which ones it writes is not decided here but by the ``solr`` key of
the fields in the schema (``README.md``, section "Solr schema"):

``flatten``
    the subfields of a repeating field that get a Solr field each, ``<prefix>_<subfield>``; a dotted path
    reaches into a subfield that has subfields itself;
``prefix``
    the start of those names when it is not the name of the field;
``text: false``
    the field is indexed under its own name, so the ``extras_<field>`` copy that CKAN adds (searched as free
    text) is dropped; a repeating field with it is dropped from the document once it is flattened, so that
    scheming makes no ``extras_<field>__<subfield>`` text of it either;
``multiple: false``
    the Solr field holds one value although the scheming field is a list: the first value is kept, and
    ``all_values`` names a second Solr field that gets all of them.

A field that holds a list and has no repeating subfields has its JSON text decoded to a real list, unless it says
``decode: false``: a plugin that runs after this one reads the text (ckanext-dataset-series reads ``in_series``).

Standard library only: the functions take the schema fields and the document and know no field name.
"""

from __future__ import annotations

import json
from typing import Any, Iterable, List, Mapping, Optional, Tuple

from ckanext.gdi_userportal.profile_packs import schema_fields

EXTRAS_PREFIX = "extras_"


def _decode(value: Any) -> Any:
    """A JSON text holding a list or an object as that list or object; anything else as it is."""
    if isinstance(value, str) and value.lstrip()[:1] in ("[", "{"):
        try:
            decoded = json.loads(value)
        except ValueError:
            return value
        if isinstance(decoded, (list, dict)):
            return decoded
    return value


def values_of(value: Any) -> List[Any]:
    """The values of a subfield: one, a list, or a JSON text holding a list. Empty values are left out."""
    value = _decode(value)
    if isinstance(value, (list, tuple)):
        return [item for item in value if item]
    return [value] if value else []


def _strings(node: Any) -> List[str]:
    """Every string in a value, however deep it is nested in lists and objects."""
    if isinstance(node, str):
        return [node] if node else []
    if isinstance(node, (list, tuple)):
        return [text for item in node for text in _strings(item)]
    if isinstance(node, Mapping):
        return [text for item in node.values() for text in _strings(item)]
    return []


def _leaf(node: Any) -> List[Any]:
    """What a path ends in: a value, the values of a list; an object stands for its name."""
    node = _decode(node)
    if isinstance(node, (list, tuple)):
        return [value for item in node for value in _leaf(item)]
    if isinstance(node, Mapping):
        return _strings(node.get("name"))
    return [node] if node else []


def _collect(node: Any, path: Tuple[str, ...]) -> List[Any]:
    """The values at ``path`` below ``node``, through lists and JSON texts on the way."""
    if not path:
        return _leaf(node)
    node = _decode(node)
    if isinstance(node, (list, tuple)):
        return [value for item in node for value in _collect(item, path)]
    if isinstance(node, Mapping):
        if path == ("name",):
            return _strings(_decode(node.get("name")))  # a name may be nested in lists and objects
        return _collect(node.get(path[0]), path[1:])
    if isinstance(node, str) and node and path == ("name",):
        return [node]  # an agent given as its name only
    return []


def _entries(raw: Any, paths: Iterable[Tuple[str, ...]]) -> Optional[List[Any]]:
    """The entries of a repeating field, or None when it holds nothing the paths could be read from."""
    raw = _decode(raw)
    if not raw:
        return None
    if isinstance(raw, Mapping):
        return [raw]
    if isinstance(raw, (list, tuple)):
        return list(raw)
    if isinstance(raw, str) and any(path[0] == "name" for path in paths):
        return [{"name": raw}]
    return None


def flatten(document: dict, field: Mapping) -> dict:
    """Write the ``solr.flatten`` subfields of a repeating field as multi valued Solr fields.

    When the field itself is not in the document, the ``extras_<field>__<subfield>`` text that CKAN made of a
    first level subfield is used instead.
    """
    paths = schema_fields.flatten_paths(field)
    if not paths:
        return document
    name, prefix = field["field_name"], schema_fields.flatten_prefix(field)
    entries = _entries(document.get(name), paths)
    for path in paths:
        if entries is not None:
            values = [value for entry in entries for value in _collect(entry, path)]
        elif len(path) == 1:
            values = values_of(document.get("%s%s__%s" % (EXTRAS_PREFIX, name, path[0])))
        else:
            values = []
        values = [value.strip() if isinstance(value, str) else value for value in values]
        values = list(dict.fromkeys(value for value in values if value != ""))
        if values:
            document["%s_%s" % (prefix, "_".join(path))] = values
    if schema_fields.solr_options(field).get("text") is False:
        # scheming would turn the list into extras_<field>__<subfield> text, with "None" for every empty value
        document.pop(name, None)
    return document


def normalise(document: dict, field: Mapping) -> dict:
    """Decode the JSON text of a list field, and drop the ``extras_`` copy of a field marked ``text: false``.

    A list or repeating field that only has its ``extras_<field>`` copy (a dataset that was not indexed through
    the schema) gets its value from there.
    """
    name = field["field_name"]
    options = schema_fields.solr_options(field)
    drops_text = options.get("text") is False
    repeating = bool(schema_fields.subfields(field))
    holds_list = (repeating or schema_fields.is_multiple(field)) and options.get("decode") is not False
    if not (drops_text or holds_list):
        return document

    extras_key = EXTRAS_PREFIX + name
    value = document.get(name)
    moved = value in (None, "") and bool(document.get(extras_key))
    if moved:
        value = document[extras_key]
    if value not in (None, ""):
        decoded = _decode(value)
        document[name] = decoded if holds_list and isinstance(decoded, list) else value
    if drops_text or (repeating and moved):
        document.pop(extras_key, None)
    return document


def keep_one_value(document: dict, field: Mapping) -> dict:
    """For a list field whose Solr field is single valued (``solr: {multiple: false}``) keep the first value.

    ``solr: {all_values: <solr field>}`` puts all of them in a second, multi valued field.
    """
    options = schema_fields.solr_options(field)
    if options.get("multiple") is not False or not schema_fields.is_multiple(field):
        return document
    name = field["field_name"]
    value = _decode(document.get(name))
    if not isinstance(value, (list, tuple)):
        return document
    values = [str(item) for item in value if item]
    if options.get("all_values") and values:
        document[options["all_values"]] = list(dict.fromkeys(values))
    if values:
        document[name] = values[0]
    else:
        document.pop(name, None)
    return document


def _named(fields: Iterable[Mapping]) -> List[Mapping]:
    return [field for field in fields or [] if isinstance(field, Mapping) and field.get("field_name")]


def normalise_all(document: dict, fields: Iterable[Mapping]) -> dict:
    for field in _named(fields):
        normalise(document, field)
    return document


def flatten_all(document: dict, fields: Iterable[Mapping]) -> dict:
    for field in _named(fields):
        flatten(document, field)
    return document


def keep_one_value_all(document: dict, fields: Iterable[Mapping]) -> dict:
    for field in _named(fields):
        keep_one_value(document, field)
    return document
