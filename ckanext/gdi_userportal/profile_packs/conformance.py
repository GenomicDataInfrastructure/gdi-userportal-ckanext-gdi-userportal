# SPDX-FileCopyrightText: 2026 Stichting Health-RI
#
# SPDX-License-Identifier: Apache-2.0

"""
Which enabled metadata profiles a dataset satisfies (ADR 0001, section 6).

Computed on demand from the dataset itself, never stored. A dataset conforms to a profile when
every property the profile makes mandatory at the dataset's access layer (PUBLIC, RESTRICTED or
NON_PUBLIC, from ``access_rights``) has a value. Nothing blocks on the outcome.

Only the presence of a value is checked: not the maximum cardinality, the vocabulary a value
comes from, the shape of a nested node, or R8's conditional rule that structured data needs
variables. Data from before a profile existed lacks values; that is a "not conformant"
answer, never an error, so every value shape is accepted here.

The rules come from the pack manifests (``Registry.conformance`` in ``generator.py``). A pack
without rules has no mandatory properties and is satisfied by every dataset.

Standard library only.
"""

from __future__ import annotations

import json
from collections.abc import Mapping

LAYERS = ("PUBLIC", "RESTRICTED", "NON_PUBLIC")
ACCESS_RIGHTS_FIELD = "access_rights"


def is_filled(value):
    """Whether ``value`` holds anything: a blank string, an empty container or null does not.

    A container is filled when anything inside it is, so a repeating field saved with one blank
    row is empty. ``False`` and ``0`` are values. A string that holds a JSON list or object is
    judged by what it decodes to, because old extras were stored that way.
    """
    if value is None:
        return False
    if isinstance(value, (bool, int, float)):
        return True
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return False
        if text[0] in "[{":
            try:
                return is_filled(json.loads(text))
            except (ValueError, RecursionError):
                return True
        return True
    if isinstance(value, Mapping):
        return any(is_filled(item) for item in value.values())
    if isinstance(value, (list, tuple, set, frozenset)):
        return any(is_filled(item) for item in value)
    return True


def access_layer(dataset):
    """``(layer, problem)``: the layer from ``access_rights``, or None and why there is none."""
    candidate = _first_text(dataset.get(ACCESS_RIGHTS_FIELD))
    if candidate is None:
        return None, "access rights is missing"
    layer = candidate.rstrip("/").rsplit("/", 1)[-1].rsplit("#", 1)[-1]
    layer = layer.strip().upper().replace("-", "_").replace(" ", "_")
    if layer in LAYERS:
        return layer, None
    return None, f"access rights {candidate!r} is not one of {', '.join(LAYERS)}"


def _first_text(value):
    if isinstance(value, str):
        text = value.strip()
        if text[:1] in ("[", "{"):  # old extras were stored JSON-encoded, as is_filled also accepts
            try:
                return _first_text(json.loads(text))
            except (ValueError, RecursionError):
                pass
        return text or None
    if isinstance(value, Mapping):
        value = list(value.values())
    if isinstance(value, (list, tuple)):
        for item in value:
            text = _first_text(item)
            if text:
                return text
    return None


def evaluate(dataset, profiles, rules):
    """The conformance of ``dataset`` to each of ``profiles``.

    ``rules`` maps a profile name to its loaded conformance document, or to None when the
    profile declares no mandatory properties. Returns::

        {"access_layer": "NON_PUBLIC" or None,
         "profiles": {name: {"conformant": bool, "mandatory": int,
                             "missing": [{"property": label, "fields": [...]}],
                             "reason": text, only when there is no access layer}},
         "conformant_profiles": [name, ...]}
    """
    layer, problem = access_layer(dataset)
    results = {}
    for name in profiles:
        layer_rules = _mandatory_properties(rules.get(name), layer)
        if layer_rules is None:
            results[name] = {"conformant": False, "mandatory": 0, "missing": [], "reason": problem}
            continue
        missing = [
            {"property": rule["property"], "fields": list(rule["fields"])}
            for rule in layer_rules
            if not any(is_filled(dataset.get(field)) for field in rule["fields"])
        ]
        results[name] = {"conformant": not missing, "mandatory": len(layer_rules), "missing": missing}
    return {
        "access_layer": layer,
        "profiles": results,
        "conformant_profiles": [name for name, result in results.items() if result["conformant"]],
    }


def evaluate_class(record, profiles, rules, kind):
    """The conformance of one distribution or dataset series (``kind``) to each of ``profiles``.

    A distribution is a resource of a dataset, a sample and an analytics distribution included (R8's shapes
    apply the distribution shape to them too). Their mandatory properties do not depend on the access layer, so
    none is needed. ``rules`` is as for ``evaluate``. Returns::

        {"profiles": {name: {"conformant": bool, "mandatory": int, "missing": [{"property", "fields"}]}},
         "conformant_profiles": [name, ...]}

    A profile that declares nothing for ``kind`` has no mandatory properties and is satisfied. Like
    ``evaluate``, whatever the record holds gives an answer, never an error.
    """
    record = record if isinstance(record, Mapping) else {}
    results = {}
    for name in profiles:
        mandatory = _class_properties(rules.get(name), kind)
        missing = [
            {"property": rule["property"], "fields": list(rule["fields"])}
            for rule in mandatory
            if not any(is_filled(record.get(field)) for field in rule["fields"])
        ]
        results[name] = {"conformant": not missing, "mandatory": len(mandatory), "missing": missing}
    return {
        "profiles": results,
        "conformant_profiles": [name for name, result in results.items() if result["conformant"]],
    }


def _class_properties(document, kind):
    classes = document.get("classes") if document else None
    return ((classes or {}).get(kind) or {}).get("mandatory", [])


def _mandatory_properties(document, layer):
    """The mandatory properties to check, ``[]`` for a profile without rules, None without a layer."""
    if document is None:
        return []
    if layer is None:
        return None
    return document["layers"][layer]["mandatory"]
