# SPDX-FileCopyrightText: 2026 Stichting Health-RI
#
# SPDX-License-Identifier: Apache-2.0

"""
Generate the mandatory-properties file of the ``healthdcat_r8`` pack from R8's own rules.

R8 publishes its cardinality and requirement level per access layer in
``healthdcat-cardinality-rules.json``. This turns the properties that are Mandatory in a layer
into ``conformance/healthdcat_r8.json``, naming the CKAN fields that carry each one (from
``conformance/healthdcat_r8_fields.yaml``). Rerun it when R8 publishes new rules::

    python3 -m ckanext.gdi_userportal.profile_packs.conformance_build \\
        --rules path/to/healthdcat-cardinality-rules.json [--check]

``--check`` writes nothing and exits 1 when the committed file differs from what the rules
produce. Standard library and PyYAML only.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

import yaml

PACK_ROOT = Path(__file__).resolve().parent
PROFILE = "healthdcat_r8"

# The rules file names the layers PUBLIC, RESTRICTED and NON-PUBLIC.
LAYERS = {"PUBLIC": "PUBLIC", "RESTRICTED": "RESTRICTED", "NON-PUBLIC": "NON_PUBLIC"}
MANDATORY = "Mandatory"
# The classes other than the dataset that the field mapping can name (see conformance.py).
CLASSES = ("distribution", "series")


class ConformanceBuildError(Exception):
    """The rules and the field mapping do not agree, or a file is unreadable."""


def build(rules_text, fields_text, profile=PROFILE, source_name="healthdcat-cardinality-rules.json"):
    """The conformance document for ``profile``. Deterministic: the same inputs give the same text."""
    try:
        rules = json.loads(rules_text)
        mapping = (yaml.safe_load(fields_text) or {}).get("properties")
    except (ValueError, yaml.YAMLError, AttributeError) as error:
        raise ConformanceBuildError(f"cannot parse the rules or the field mapping: {error}") from error
    if not isinstance(rules, dict) or not isinstance(mapping, dict):
        raise ConformanceBuildError("the rules must be an object per layer and the mapping a 'properties' object")

    unknown_layers = set(rules) - set(LAYERS)
    if unknown_layers:
        raise ConformanceBuildError(f"unknown layers in the rules: {', '.join(sorted(unknown_layers))}")

    layers = {}
    mandatory_labels = set()
    for source_layer, layer in LAYERS.items():
        properties = rules.get(source_layer)
        if not isinstance(properties, dict):
            raise ConformanceBuildError(f"the rules have no layer {source_layer}")
        mandatory = []
        for label, rule in properties.items():
            if _is_mandatory(source_layer, label, rule):
                mandatory_labels.add(label)
                mandatory.append(
                    {"property": label, "cardinality": rule["card"], "fields": _fields(mapping, label)}
                )
        layers[layer] = {"mandatory": mandatory}

    stale = sorted(set(mapping) - mandatory_labels)
    if stale:
        raise ConformanceBuildError(
            f"the field mapping names properties that are not mandatory in any layer: {', '.join(stale)}"
        )

    document = {
        "profile": profile,
        "source": {"file": source_name, "sha256": hashlib.sha256(rules_text.encode("utf-8")).hexdigest()},
        "layers": layers,
    }
    document.update(_class_section(fields_text))
    return json.dumps(document, indent=2, ensure_ascii=False) + "\n"


def _class_section(fields_text):
    """``{"classes": ...}`` when the field mapping has class rules, else nothing to add."""
    rules = _class_rules((yaml.safe_load(fields_text) or {}).get("classes"))
    return {"classes": rules} if rules else {}


def _class_rules(classes):
    """The mandatory properties of the classes other than the dataset, from the field mapping.

    R8's cardinality rules describe the dataset only. For distributions and dataset series the mandatory
    properties are the ones R8's SHACL shapes require, the same in every access layer, so they are kept in the
    field mapping next to the property-to-field map and carried over as they are.
    """
    if classes is None:
        return {}
    if not isinstance(classes, dict) or set(classes) - set(CLASSES):
        raise ConformanceBuildError(f"'classes' in the field mapping must name only: {', '.join(CLASSES)}")
    document = {}
    for kind, body in classes.items():
        properties = body.get("properties") if isinstance(body, dict) else None
        if not isinstance(properties, dict) or not properties:
            raise ConformanceBuildError(f"class {kind!r} needs a 'properties' mapping")
        mandatory = []
        for label, rule in properties.items():
            if not isinstance(rule, dict) or not isinstance(rule.get("cardinality"), str):
                raise ConformanceBuildError(f"class {kind!r}: property {label!r} needs a 'cardinality' and 'fields'")
            mandatory.append(
                {"property": label, "cardinality": rule["cardinality"], "fields": _fields({label: rule.get("fields")}, label)}
            )
        document[kind] = {"source": str(body.get("source", "")), "mandatory": mandatory}
    return document


def _is_mandatory(layer, label, rule):
    if not isinstance(rule, dict) or "card" not in rule or "requirement" not in rule:
        raise ConformanceBuildError(f"{layer}: property {label!r} has no 'card' and 'requirement'")
    by_requirement = rule["requirement"] == MANDATORY
    by_cardinality = str(rule["card"]).split("..")[0].strip() not in ("0", "")
    if by_requirement != by_cardinality:
        raise ConformanceBuildError(
            f"{layer}: property {label!r} is {rule['requirement']!r} with cardinality {rule['card']!r}; "
            "the rules disagree with themselves"
        )
    return by_requirement


def _fields(mapping, label):
    fields = mapping.get(label)
    if not fields or not isinstance(fields, list) or not all(isinstance(f, str) and f for f in fields):
        raise ConformanceBuildError(
            f"mandatory property {label!r} has no CKAN fields in the field mapping; add it to "
            "conformance/healthdcat_r8_fields.yaml"
        )
    return fields


def main(argv=None):
    parser = argparse.ArgumentParser(description=(__doc__ or "").split("\n\n")[0])
    parser.add_argument("--rules", required=True, type=Path, help="healthdcat-cardinality-rules.json")
    parser.add_argument("--fields", type=Path, default=PACK_ROOT / "conformance" / f"{PROFILE}_fields.yaml")
    parser.add_argument("--output", type=Path, default=PACK_ROOT / "conformance" / f"{PROFILE}.json")
    parser.add_argument("--check", action="store_true", help="exit 1 when the output file is out of date")
    args = parser.parse_args(argv)

    try:
        text = build(
            args.rules.read_text(encoding="utf-8"),
            args.fields.read_text(encoding="utf-8"),
            source_name=args.rules.name,
        )
    except (OSError, ConformanceBuildError) as error:
        print(f"[conformance-build] ERROR {error}", file=sys.stderr)
        return 1

    if args.check:
        current = args.output.read_text(encoding="utf-8") if args.output.is_file() else None
        if current != text:
            print(f"[conformance-build] {args.output} is out of date; rerun without --check", file=sys.stderr)
            return 1
        return 0
    args.output.write_text(text, encoding="utf-8")
    print(f"[conformance-build] wrote {args.output}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
