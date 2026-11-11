# SPDX-FileCopyrightText: 2026 Stichting Health-RI
#
# SPDX-License-Identifier: Apache-2.0

"""
The Solr schema that follows the generated dataset schema: ``derive_fields`` makes a Solr field of
every dataset field that ``schema.xml`` does not declare, ``sync`` applies the difference to the
running core through the Solr Schema API (it never deletes a field), and ``check`` is the drift test.
The rules, including the ``solr`` key that overrides a derived field, are in ``README.md``, section
"Solr schema".

It runs from the container start scripts and imports nothing but the standard library and PyYAML::

    python3 -m ckanext.gdi_userportal.profile_packs.solr_schema sync --dataset-schema DIR/dataset.yaml
"""

from __future__ import annotations

import argparse
import dataclasses
import json
import os
import sys
import time
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Tuple

import yaml

from ckanext.gdi_userportal.profile_packs.schema_fields import (
    FLUENT_TEXT_PRESETS,
    by_name,
    flatten_paths,
    flattened_solr_fields,
    is_multiple,
    solr_options,
    subfields,
)

DEFAULT_SCHEMA_XML = Path(__file__).resolve().parents[3] / "solr" / "schema.xml"
ENV_SOLR_URL = "CKAN_SOLR_URL"
CATCH_ALL = "*"

# A validator that fixes the type of the values; the Solr type it maps to.
INFERRED_TYPES = {"int_validator": "long", "boolean_validator": "boolean"}

# What a field gets when its ``solr`` key says nothing: stored (the Solr UI shows the value; it costs disk, CKAN
# itself does not need it), indexed, and for a number or a date ``docValues``, which sorting, range filters and
# range facets need.
DEFAULT_STORED = True
DOC_VALUES_TYPES = {"int", "long", "float", "double", "pint", "plong", "pfloat", "pdouble", "date", "pdate", "boolean"}

# The fields CKAN indexes itself, whatever the dataset schema says: they stay declared in ``schema.xml``.
CKAN_OWN_FIELDS = frozenset(
    {"id", "name", "title", "notes", "url", "version", "license_id", "author", "author_email", "maintainer",
     "maintainer_email", "state", "owner_org", "private", "type"}
)

# Attributes of a field that are compared, with the value Solr uses when the attribute is absent.
ATTRIBUTES = {"type": None, "multiValued": False, "indexed": True, "stored": True, "docValues": None}


class SolrSchemaError(Exception):
    pass


@dataclasses.dataclass
class SolrSchema:
    """The fields, dynamic fields, copy fields and field type names of a Solr schema."""

    fields: Dict[str, dict] = dataclasses.field(default_factory=dict)
    dynamic_fields: Dict[str, dict] = dataclasses.field(default_factory=dict)
    copy_fields: List[Tuple[str, str]] = dataclasses.field(default_factory=list)
    field_types: set = dataclasses.field(default_factory=set)


def _boolean(value):
    if isinstance(value, str):
        return value.strip().lower() == "true"
    return bool(value)


def _attributes(element) -> dict:
    spec = {"name": element.get("name"), "type": element.get("type")}
    for key in ("multiValued", "indexed", "stored", "docValues", "required"):
        if element.get(key) is not None:
            spec[key] = _boolean(element.get(key))
    return spec


def parse_schema_xml(path) -> SolrSchema:
    """Read ``schema.xml``: its fields, dynamic fields, copy fields and the names of its field types."""
    root = ET.parse(str(path)).getroot()
    schema = SolrSchema()
    for element in root.iter():
        if element.tag in ("fieldType", "fieldtype"):
            schema.field_types.add(element.get("name"))
        elif element.tag == "field":
            schema.fields[element.get("name")] = _attributes(element)
        elif element.tag == "dynamicField":
            schema.dynamic_fields[element.get("name")] = _attributes(element)
        elif element.tag == "copyField":
            schema.copy_fields.append((element.get("source"), element.get("dest")))
    return schema


def matching_dynamic_field(name: str, dynamic_fields: Iterable[str]) -> Optional[str]:
    """The dynamic field (other than the catch-all) that Solr applies to a field name, if any."""
    for pattern in dynamic_fields:
        if pattern == CATCH_ALL:
            continue
        if (pattern.startswith("*") and name.endswith(pattern[1:])) or (
            pattern.endswith("*") and name.startswith(pattern[:-1])
        ):
            return pattern
    return None


def inferred_type(field: dict) -> str:
    """The Solr type for the values of a scheming field, from its validators; a string when none says more."""
    for validator in str(field.get("validators", "")).split():
        if validator in INFERRED_TYPES:
            return INFERRED_TYPES[validator]
    return "string"


def solr_settings(field: dict) -> dict:
    """The Solr field a scheming field gets: what follows from the field, overridden by its ``solr`` key."""
    override = field.get("solr") or {}
    settings = {
        "name": field["field_name"],
        "type": override.get("type", inferred_type(field)),
        "indexed": bool(override.get("index", True)),
        "stored": bool(override.get("store", DEFAULT_STORED)),
        "multiValued": bool(override.get("multiple", is_multiple(field))),
    }
    if settings["type"] in DOC_VALUES_TYPES:
        settings["docValues"] = True
    return settings


def _is_row_field(field: dict) -> bool:
    """A field that holds objects: a repeating field (rows) or a text per language (a map). The indexing writes
    the values of its subfields (``solr: {flatten}``) and the free text, never the objects, so it has no Solr
    field of its own."""
    return bool(subfields(field)) or field.get("preset") in FLUENT_TEXT_PRESETS


def derive_fields(dataset_fields: Iterable[dict], base: SolrSchema) -> List[dict]:
    """The Solr fields for the dataset fields that ``schema.xml`` does not declare, in schema order.

    A field of objects gets none (see ``_is_row_field``). The fields the indexing fills from it
    (``solr: {flatten: ...}``) follow the dataset fields: a multi valued string, indexed and stored.
    """
    dataset_fields = list(dataset_fields)
    derived = []
    for field in dataset_fields:
        name = field["field_name"]
        if _is_row_field(field) or name in base.fields or matching_dynamic_field(name, base.dynamic_fields):
            continue
        derived.append(solr_settings(field))
    known = {spec["name"] for spec in derived}
    for name in flattened_solr_fields(dataset_fields):
        if name in known or name in base.fields or matching_dynamic_field(name, base.dynamic_fields):
            continue
        known.add(name)
        derived.append({"name": name, "type": "string", "indexed": True, "stored": DEFAULT_STORED, "multiValued": True})
    return derived


def wanted_schema(base: SolrSchema, dataset_fields: Iterable[dict]) -> SolrSchema:
    """``schema.xml`` plus the fields derived from the dataset schema."""
    wanted = SolrSchema(
        fields=dict(base.fields),
        dynamic_fields=dict(base.dynamic_fields),
        copy_fields=list(base.copy_fields),
        field_types=set(base.field_types),
    )
    for spec in derive_fields(dataset_fields, base):
        wanted.fields[spec["name"]] = spec
    return wanted


def _has_subfield(field: dict, path: Tuple[str, ...]) -> bool:
    """Whether ``path`` (names of subfields, each inside the one before) exists below ``field``."""
    named = by_name(subfields(field))
    return path[0] in named and (len(path) == 1 or _has_subfield(named[path[0]], path[1:]))


def _solr_field(wanted: SolrSchema, name: str) -> Optional[dict]:
    """The field Solr would index ``name`` into: the declared or derived field, else a dynamic field."""
    spec = wanted.fields.get(name)
    if spec is None:
        pattern = matching_dynamic_field(name, wanted.dynamic_fields)
        spec = wanted.dynamic_fields.get(pattern) if pattern else None
    return spec


def _flatten_problems(wanted: SolrSchema, dataset_fields: List[dict]) -> List[str]:
    problems = [
        "dataset_fields.%s flattens '%s', which the field has no subfield for" % (field["field_name"], ".".join(path))
        for field in dataset_fields
        for path in flatten_paths(field)
        if not _has_subfield(field, path)
    ]
    for name in flattened_solr_fields(dataset_fields):
        spec = _solr_field(wanted, name)
        if spec is not None and not spec.get("multiValued", False):
            problems.append("the indexing fills the Solr field %s with a list but it is single valued" % name)
    return problems


def _type_problems(base: SolrSchema, dataset_fields: List[dict]) -> List[str]:
    return [
        "dataset_fields.%s asks for the Solr type '%s', which solr/schema.xml does not define"
        % (field["field_name"], solr_options(field)["type"])
        for field in dataset_fields
        if solr_options(field).get("type") and solr_options(field)["type"] not in base.field_types
    ]


def _list_problems(wanted: SolrSchema, dataset_fields: List[dict]) -> List[str]:
    problems = []
    for field in dataset_fields:
        # solr: {multiple: false}: the indexing keeps one value of the list; a field of objects is not indexed itself
        if solr_options(field).get("multiple") is False or not is_multiple(field) or _is_row_field(field):
            continue
        spec = _solr_field(wanted, field["field_name"])
        if spec is not None and not spec.get("multiValued", False):
            problems.append(
                "dataset_fields.%s is a list in the schema but its Solr field is single valued; "
                "make it multiValued in solr/schema.xml, or flatten it before indexing" % field["field_name"]
            )
    return problems


def _duplicate_problems(base: SolrSchema, dataset_fields: List[dict]) -> List[str]:
    """A dataset field (or a field made of one) that ``schema.xml`` declares as well: the declaration in
    ``schema.xml`` wins, so the ``solr`` key of the field would silently do nothing."""
    names = [field["field_name"] for field in dataset_fields] + list(flattened_solr_fields(dataset_fields))
    return [
        "%s is declared in solr/schema.xml and made from the dataset schema: remove it from schema.xml "
        "(describe it with the 'solr' key of the field when it is not a plain stored string)" % name
        for name in dict.fromkeys(names)
        if name in base.fields and name not in CKAN_OWN_FIELDS
    ]


def check(base: SolrSchema, dataset_fields: Iterable[dict]) -> List[str]:
    """The dataset fields that ``schema.xml`` declares as well as the dataset schema, and those whose Solr field
    is single valued while the scheming field holds a list.

    And the flattened fields (``solr: {flatten: ...}``): they must name subfields the field has, and the
    Solr field they are written to must be multi valued.
    """
    dataset_fields = list(dataset_fields)
    wanted = wanted_schema(base, dataset_fields)
    return (
        _duplicate_problems(base, dataset_fields)
        + _flatten_problems(wanted, dataset_fields)
        + _type_problems(base, dataset_fields)
        + _list_problems(wanted, dataset_fields)
    )


# -- compare the wanted schema with the running core ----------------------------------------------

Command = Tuple[str, dict]


def _normalised(spec: dict) -> dict:
    return {key: spec.get(key, default) for key, default in ATTRIBUTES.items()}


def _differs(wanted: dict, live: dict) -> bool:
    wanted, live = _normalised(wanted), _normalised(live)
    return any(wanted[key] != live[key] for key in ATTRIBUTES if wanted[key] is not None)


def plan(wanted: SolrSchema, live: SolrSchema) -> Tuple[List[Command], List[str]]:
    """The Schema API commands that bring the core to the wanted schema, and the problems that need more."""
    commands: List[Command] = []
    problems: List[str] = []

    missing_types = sorted(
        {spec["type"] for spec in [*wanted.fields.values(), *wanted.dynamic_fields.values()]} - live.field_types
    )
    for field_type in missing_types:
        problems.append(
            "the running core has no field type '%s': recreate the core from the Solr image" % field_type
        )

    for kind, wanted_group, live_group in (
        ("field", wanted.fields, live.fields),
        ("dynamic-field", wanted.dynamic_fields, live.dynamic_fields),
    ):
        for name, spec in wanted_group.items():
            if spec["type"] in missing_types:
                continue
            if name not in live_group:
                commands.append(("add-" + kind, spec))
            elif _differs(spec, live_group[name]):
                commands.append(("replace-" + kind, spec))

    live_copies = set(live.copy_fields)
    for source, dest in wanted.copy_fields:
        if (source, dest) not in live_copies:
            commands.append(("add-copy-field", {"source": source, "dest": dest}))

    return commands, problems


# -- the running core -----------------------------------------------------------------------------


def _get(url: str) -> dict:
    with urllib.request.urlopen(url, timeout=30) as response:
        return json.load(response)


def read_live_schema(solr_url: str) -> SolrSchema:
    base = solr_url.rstrip("/") + "/schema"
    live = SolrSchema()
    for spec in _get(base + "/fields")["fields"]:
        live.fields[spec["name"]] = spec
    for spec in _get(base + "/dynamicfields")["dynamicFields"]:
        live.dynamic_fields[spec["name"]] = spec
    for spec in _get(base + "/copyfields")["copyFields"]:
        live.copy_fields.append((spec["source"], spec["dest"]))
    live.field_types = {spec["name"] for spec in _get(base + "/fieldtypes")["fieldTypes"]}
    return live


def apply_commands(solr_url: str, commands: Iterable[Command]) -> None:
    url = solr_url.rstrip("/") + "/schema"
    for command, spec in commands:
        request = urllib.request.Request(
            url, data=json.dumps({command: spec}).encode("utf-8"), headers={"Content-Type": "application/json"}
        )
        try:
            with urllib.request.urlopen(request, timeout=60) as response:
                body = json.load(response)
        except urllib.error.HTTPError as error:
            raise SolrSchemaError("%s %s: HTTP %s %s" % (command, spec, error.code, error.read()[:300]))
        if body.get("errors"):
            raise SolrSchemaError("%s %s: %s" % (command, spec, body["errors"]))


def wait_for_solr(solr_url: str, seconds: int) -> bool:
    deadline = time.monotonic() + seconds
    while True:
        try:
            _get(solr_url.rstrip("/") + "/schema/fieldtypes")
            return True
        except (urllib.error.URLError, OSError, ValueError):
            if time.monotonic() >= deadline:
                return False
            time.sleep(3)


def describe(command: Command) -> str:
    name, spec = command
    if name.endswith("copy-field"):
        return "%s %s -> %s" % (name, spec["source"], spec["dest"])
    flags = ", ".join("%s=%s" % (key, spec[key]) for key in ("type", "multiValued", "indexed", "stored") if key in spec)
    return "%s %s (%s)" % (name, spec["name"], flags)


# -- command line ---------------------------------------------------------------------------------


def _load_dataset_fields(path) -> List[dict]:
    with open(str(path), encoding="utf-8") as handle:
        return yaml.safe_load(handle)["dataset_fields"]


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("action", choices=["sync", "check"])
    parser.add_argument("--dataset-schema", required=True, help="the generated dataset.yaml")
    parser.add_argument("--schema-xml", default=str(DEFAULT_SCHEMA_XML))
    parser.add_argument("--solr-url", default=os.environ.get(ENV_SOLR_URL))
    parser.add_argument("--dry-run", action="store_true", help="sync: print the changes, apply nothing")
    parser.add_argument("--wait", type=int, default=60, help="sync: seconds to wait for Solr to answer")
    args = parser.parse_args(argv)

    base = parse_schema_xml(args.schema_xml)
    dataset_fields = _load_dataset_fields(args.dataset_schema)

    if args.action == "check":
        problems = check(base, dataset_fields)
        for problem in problems:
            print("solr-schema: " + problem, file=sys.stderr)
        return 1 if problems else 0

    if not args.solr_url:
        print("solr-schema: no Solr URL (%s or --solr-url)" % ENV_SOLR_URL, file=sys.stderr)
        return 1
    if not wait_for_solr(args.solr_url, args.wait):
        print("solr-schema: Solr does not answer at %s" % args.solr_url, file=sys.stderr)
        return 1

    commands, problems = plan(wanted_schema(base, dataset_fields), read_live_schema(args.solr_url))
    for problem in problems:
        print("solr-schema: " + problem, file=sys.stderr)
    for command in commands:
        print("solr-schema: " + describe(command))
    if not commands:
        print("solr-schema: the core already has the wanted schema")
    elif args.dry_run:
        print("solr-schema: dry run, nothing applied")
    else:
        apply_commands(args.solr_url, commands)
        print(
            "solr-schema: applied %d change(s); datasets indexed before this change keep their old "
            "index until they are reindexed: run 'ckan search-index rebuild'" % len(commands)
        )
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
