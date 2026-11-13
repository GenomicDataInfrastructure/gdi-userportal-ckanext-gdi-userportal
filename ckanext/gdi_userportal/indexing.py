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
``text``
    whether the field is searched as free text: it is, unless it says ``text: false``. Every text in it (every
    language, every subfield) goes into Solr's free-text field, and for a URI or code that has translations
    (CKAN's ``term_translation``) its labels in every language too, so that "Utrecht" finds a dataset that has
    ``.../place/NLD_UTC`` in a property. The JSON text CKAN made of the field (``extras_<field>``) and the objects
    of a repeating field are not indexed: Solr would search their braces and keys (``free_text_all``);
``canonical_prefix``
    the URI prefix the values of the field are indexed with: a value that starts with the same prefix in the other
    scheme (``https`` for ``http``) gets this one, and doubles go (``canonicalise_uris``);
``multiple: false``
    the Solr field holds one value although the scheming field is a list: the first value is kept, and
    ``all_values`` names a second Solr field that gets all of them.

A multilingual keyword field (preset ``fluent_tags``, named ``<x>_translated``) adds its keywords to ``<x>``
(``merge_translated_keywords``): no mark is needed, as for the free text.

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


def _other_scheme(prefix: str) -> str:
    """The prefix with the other URI scheme (``http`` for ``https`` and the other way round); empty for neither."""
    for scheme, other in (("http://", "https://"), ("https://", "http://")):
        if prefix.startswith(scheme):
            return other + prefix[len(scheme) :]
    return ""


def canonicalise_uris(document: dict, field: Mapping) -> dict:
    """Index the URIs of a field with the prefix its ``solr: {canonical_prefix}`` names, without doubles.

    ``https://publications.europa.eu/.../data-theme/HEAL`` and the ``http`` form are one term for the filters; the
    prefix says which form is the canonical one. Only a text that starts with the other form of the prefix changes.
    """
    prefix = schema_fields.canonical_prefix(field)
    other = _other_scheme(prefix)
    name = field["field_name"]
    value = document.get(name)
    if not prefix or not other or value is None:
        return document

    def canonical(item):
        return prefix + item[len(other) :] if isinstance(item, str) and item.startswith(other) else item

    if not isinstance(value, list):
        document[name] = canonical(value)
        return document
    items, seen = [], set()
    for item in map(canonical, value):
        if isinstance(item, str):
            if item in seen:
                continue
            seen.add(item)
        items.append(item)
    document[name] = items
    return document


def merge_translated_keywords(document: dict, field: Mapping) -> dict:
    """Add the keywords of a multilingual keyword field (``tags_translated``) to the field it translates (``tags``).

    Keywords somebody typed in one language are then found by the filter on the plain field too. A keyword is
    trimmed, a blank one is left out, and one the field already has is not added twice.
    """
    base = schema_fields.translated_keywords_of(field)
    if not base:
        return document
    raw = document.get(EXTRAS_PREFIX + field["field_name"])
    if not raw:
        return document
    try:
        translated = json.loads(raw) if isinstance(raw, str) else raw
    except ValueError:
        return document
    if not isinstance(translated, dict):
        return document

    existing = document.get(base) or []
    if isinstance(existing, str):
        existing = [existing]
    merged = list(existing)
    seen = set(merged)
    for keywords in translated.values():
        for keyword in keywords if isinstance(keywords, list) else []:
            if isinstance(keyword, str) and keyword.strip() and keyword.strip() not in seen:
                seen.add(keyword.strip())
                merged.append(keyword.strip())
    document[base] = merged
    return document


def normalise_all(document: dict, fields: Iterable[Mapping]) -> dict:
    for field in _named(fields):
        normalise(document, field)
    return document


def canonicalise_uris_all(document: dict, fields: Iterable[Mapping]) -> dict:
    for field in _named(fields):
        canonicalise_uris(document, field)
    return document


def merge_translated_keywords_all(document: dict, fields: Iterable[Mapping]) -> dict:
    for field in _named(fields):
        merge_translated_keywords(document, field)
    return document


def flatten_all(document: dict, fields: Iterable[Mapping]) -> dict:
    for field in _named(fields):
        flatten(document, field)
    return document


def keep_one_value_all(document: dict, fields: Iterable[Mapping]) -> dict:
    for field in _named(fields):
        keep_one_value(document, field)
    return document


FREE_TEXT_FIELD = "text"
RESOURCE_EXTRAS_PREFIX = "res_extras_"
_MAX_TERM_LENGTH = 200  # a longer text is a description, not a term that has a label


def _texts(node: Any) -> List[str]:
    """Every text in a value at any depth (a text per language, the subfields of a row); JSON texts are read."""
    node = _decode(node)
    if isinstance(node, str):
        text = node.strip()
        return [text] if text and text != "None" else []
    if isinstance(node, Mapping):
        return [text for item in node.values() for text in _texts(item)]
    if isinstance(node, (list, tuple)):
        return [text for item in node for text in _texts(item)]
    return []


def _is_structure(value: Any) -> bool:
    """A value that is an object, or a list holding objects: JSON that Solr can do nothing with."""
    value = _decode(value)
    return isinstance(value, Mapping) or (
        isinstance(value, (list, tuple)) and any(isinstance(item, Mapping) for item in value)
    )


def _field_texts(document: dict, name: str) -> List[str]:
    """What a field says: its own value, or its ``extras_`` copy, and the texts scheming made of its subfields."""
    value = document.get(name)
    if value in (None, ""):
        value = document.get(EXTRAS_PREFIX + name)
    texts = _texts(value)
    prefix = "%s%s__" % (EXTRAS_PREFIX, name)
    for key, item in document.items():
        if key.startswith(prefix):
            texts.extend(_texts(item))
    return texts


def _drop_json_copies(document: dict, name: str) -> None:
    """The ``extras_`` copies of a field and the object it holds: JSON text and objects are not searched."""
    document.pop(EXTRAS_PREFIX + name, None)
    prefix = "%s%s__" % (EXTRAS_PREFIX, name)
    for key in [key for key in document if key.startswith(prefix)]:
        del document[key]
    if _is_structure(document.get(name)):
        del document[name]


def _lookupable(text: str) -> bool:
    """Whether a text can be a term that has a label: a URI or a code, not a sentence."""
    return len(text) <= _MAX_TERM_LENGTH and not any(char.isspace() for char in text)


def free_text_all(
    document: dict,
    fields: Iterable[Mapping],
    translate=None,
    resource_fields: Iterable[Mapping] = (),
) -> dict:
    """Put what the fields say, and the labels of their terms, in the free-text Solr field.

    A field is searched as free text unless it says ``solr: {text: false}``: every text in it, in every language
    and subfield, and for a URI or code that has translations (CKAN's ``term_translation``) its labels in every
    language, so that "Utrecht" finds the dataset that has ``.../place/NLD_UTC`` in a property. The JSON text
    CKAN made of the field (``extras_<field>``) and the objects of a repeating field are dropped from the
    document: Solr would index their braces and keys, or the objects as one string.

    ``translate`` takes a list of terms and gives ``{term: [labels]}``. The labels of the terms in the extras of
    the distributions (``res_extras_*``, which Solr copies to the free text itself) are added too.
    """
    texts: List[str] = []
    for field in _named(fields):
        name = field["field_name"]
        if schema_fields.solr_options(field).get("text") is not False:
            texts.extend(_field_texts(document, name))
        _drop_json_copies(document, name)

    skipped = {
        RESOURCE_EXTRAS_PREFIX + field["field_name"]
        for field in _named(resource_fields)
        if schema_fields.solr_options(field).get("text") is False
    }
    resource_texts = [
        text
        for key, value in document.items()
        if key.startswith(RESOURCE_EXTRAS_PREFIX) and key not in skipped
        for text in _texts(value)
    ]

    terms = [text for text in dict.fromkeys(texts + resource_texts) if _lookupable(text)]
    labels = translate(terms) if translate and terms else {}

    found = []
    for text in texts:
        found.append(text)
        found.extend(labels.get(text, []))
    for text in resource_texts:
        found.extend(labels.get(text, []))

    existing = document.get(FREE_TEXT_FIELD) or []
    existing = [existing] if isinstance(existing, str) else list(existing)
    found = list(dict.fromkeys(item for item in existing + found if item))
    if found:
        document[FREE_TEXT_FIELD] = found
    return document
