# SPDX-FileCopyrightText: 2026 Stichting Health-RI
#
# SPDX-License-Identifier: Apache-2.0

"""
Profile pack registry and dataset schema generator.

A deployment enables one or more metadata profiles ("packs"). Each pack names the
schema fragments it needs; this module merges the fragments of the enabled packs
into one scheming ``dataset`` schema, because scheming 3.1.0 cannot compose
schemas at runtime.

It runs from the container start scripts, before ``prerun.py`` loads CKAN, so it
imports nothing but the standard library and PyYAML::

    python3 -m ckanext.gdi_userportal.profile_packs.generator --output-dir DIR

It writes ``dataset.yaml`` and ``provenance.json`` into DIR and prints the CKAN
config options to apply (one ``key = value`` per line) on stdout. Messages go to
stderr and any failure exits 1.

Layout (see ``README.md``)::

    packs/<name>.yaml        manifest: fragments, rdf_profiles, redefines
    fragments/<name>.yaml    partial schema: header keys, dataset_fields, resource_fields
    snippets/<name>.yaml     reusable YAML, referenced from fragments with ``!snippet <name>``
"""

from __future__ import annotations

import argparse
import copy
import dataclasses
import importlib.util
import json
import logging
import os
import re
import sys
import tempfile
import typing
from pathlib import Path

import yaml

log = logging.getLogger("metadata-profiles")

PACK_ROOT = Path(__file__).resolve().parent

DEFAULT_PROFILE = "gdi_current"
ENV_PROFILES = "GDI_METADATA_PROFILES"
ENV_MAIN_PROFILE = "GDI_METADATA_MAIN_PROFILE"
# The languages the edit form offers for the multilingual fields, in this order (a space or comma separated
# list of codes). Unset: the languages the catalogue offers (the CKAN setting below) and, without that, the
# list of the schemas, which is "en nl".
ENV_FORM_LANGUAGES = "GDI_METADATA_FORM_LANGUAGES"
# The languages the catalogue offers (a CKAN setting): the form languages when ``ENV_FORM_LANGUAGES`` is unset
ENV_LOCALES_OFFERED = "CKAN__LOCALES_OFFERED"
# The language of the plain title and description, and the one text falls back to (a CKAN setting)
ENV_LOCALE_DEFAULT = "CKAN__LOCALE_DEFAULT"
SERIES_FILENAME = "dataset_series.yaml"
_LANGUAGE_CODE = re.compile(r"^[a-z]{2,3}(?:_[A-Za-z0-9]+)?$")

# The CKAN config options the generator writes, and runtime code reads instead of the environment.
OPTION_PROFILES = "ckanext.dcat.metadata_profiles"
OPTION_MAIN_PROFILE = "ckanext.dcat.metadata_profiles.main"

RDF_PROFILE_ENTRY_POINT_GROUP = "ckan.rdf.profiles"

# Lists of scheming fields. They merge per field; every other key of a fragment is a
# header key (``scheming_version``, ``form_languages``, ...) and merges as a whole.
FIELD_SECTIONS = ("dataset_fields", "resource_fields")

# Schemas that do not vary per profile; they stay static files.
STATIC_SCHEMAS = ("ckanext.gdi_userportal:scheming/schemas/dataset_series_multilingual.yaml",)

# The generated schema uses these presets, and prerun.py loads it before setup_scheming.sh
# could have configured them, so they are set together with the schema.
SCHEMING_PRESETS = (
    "ckanext.scheming:presets.json",
    "ckanext.dcat.schemas:presets.yaml",
    "ckanext.fluent:presets.json",
    "ckanext.gdi_userportal:scheming/presets/gdi_presets.yaml",
    "ckanext.dataset_series.schemas:presets.yaml",
)

# The access layers a conformance file carries rules for (see conformance.py).
ACCESS_LAYERS = ("PUBLIC", "RESTRICTED", "NON_PUBLIC")
# The classes other than the dataset a conformance file can carry rules for, not per access layer.
CLASS_KINDS = ("distribution", "series")

SCHEMA_FILENAME = "dataset.yaml"
PROVENANCE_FILENAME = "provenance.json"

_NAME = re.compile(r"^[a-z][a-z0-9_]*$")
_SEPARATORS = re.compile(r"[,\s]+")
_MANIFEST_KEYS = {
    "name", "fragments", "rdf_profiles", "redefines", "conformance", "keep_extras", "series_schema", "overrides",
    "field_order",
}
FIELD_ORDERS = ("fragments", "alphabetical")
# With an alphabetical order these come first, in this order: the title and the description.
LEADING_FIELDS = {
    "dataset_fields": ("title_translated", "notes_translated"),
    "resource_fields": ("name_translated", "description_translated"),
    # the subfields of access_services (dcat:DataService), ordered by hand in the R8 fragment
    "data_service_fields": ("title", "description"),
}
_SCHEMA_REFERENCE = re.compile(r"^[A-Za-z_][\w.]*:[\w./-]+\.ya?ml$")


class ProfileError(Exception):
    """A configuration or pack definition error. The container must not start."""


# --- Loading ---------------------------------------------------------------------


class _SnippetRef:
    """Placeholder for ``!snippet <name>``, replaced once the fragment is loaded."""

    def __init__(self, name):
        self.name = name


class _PackLoader(yaml.SafeLoader):
    pass


_PackLoader.add_constructor(
    "!snippet", lambda loader, node: _SnippetRef(loader.construct_scalar(node))
)


class _NoAliasDumper(yaml.SafeDumper):
    """Scheming reads the output with a plain loader; repeat content instead of aliasing it."""

    def ignore_aliases(self, data):
        return True


@dataclasses.dataclass(frozen=True)
class Pack:
    name: str
    fragments: tuple
    rdf_profiles: tuple
    redefines: frozenset
    # Path of the generated mandatory-properties file, relative to the registry root. A pack
    # without one has no mandatory properties.
    conformance: typing.Optional[str] = None
    # Dataset fields that shared RDF code keeps as free extras whichever profile is enabled, so
    # retiring this pack must not prune them.
    keep_extras: frozenset = frozenset()
    # The static scheming schema of the dataset series (module:path/to/file.yaml); with several
    # packs enabled the first listed pack that has one decides.
    series_schema: typing.Optional[str] = None
    # "<section>.<field_name>" -> keys that replace those of the field for this pack only; a key set
    # to null removes it (a preset the pack replaces by its own subfields). A field that ends up
    # differing between packs still needs a ``redefines`` entry.
    overrides: typing.Mapping = dataclasses.field(default_factory=dict)
    # "fragments" (first occurrence along the fragments) or "alphabetical" (by label, the title and
    # the description first); with several packs enabled the first listed pack decides.
    field_order: str = "fragments"


class Registry:
    """The packs, fragments and snippets found under one root directory."""

    def __init__(self, root=PACK_ROOT):
        self.root = Path(root)
        self._fragments = {}
        self._snippets = {}

    def pack_names(self):
        return sorted(path.stem for path in (self.root / "packs").glob("*.yaml"))

    def pack(self, name):
        _check_name("profile", name)
        path = self.root / "packs" / f"{name}.yaml"
        if not path.is_file():
            raise ProfileError(
                f"unknown metadata profile '{name}'. Known profiles: {', '.join(self.pack_names()) or 'none'}"
            )
        manifest = self._load(path)
        if not isinstance(manifest, dict):
            raise ProfileError(f"{path}: a pack manifest must be a mapping")
        unknown = set(manifest) - _MANIFEST_KEYS
        if unknown:
            raise ProfileError(f"{path}: unknown manifest keys: {', '.join(sorted(unknown))}")
        if manifest.get("name") != name:
            raise ProfileError(f"{path}: 'name' must be '{name}', found {manifest.get('name')!r}")
        fragments = _string_list(path, manifest, "fragments", required=True)
        rdf_profiles = _string_list(path, manifest, "rdf_profiles", required=True)
        redefines = _string_list(path, manifest, "redefines", required=False)
        keep_extras = _string_list(path, manifest, "keep_extras", required=False)
        conformance = manifest.get("conformance")
        if conformance is not None and not isinstance(conformance, str):
            raise ProfileError(f"{path}: 'conformance' must be a path relative to the pack root")
        series_schema = manifest.get("series_schema")
        if series_schema is not None and not (isinstance(series_schema, str) and _SCHEMA_REFERENCE.match(series_schema)):
            raise ProfileError(f"{path}: 'series_schema' must look like 'module.name:path/to/schema.yaml'")
        overrides = manifest.get("overrides") or {}
        if not (
            isinstance(overrides, dict)
            and all(isinstance(k, str) and isinstance(v, dict) and v for k, v in overrides.items())
        ):
            raise ProfileError(f"{path}: 'overrides' must map '<section>.<field_name>' to the keys to replace")
        field_order = manifest.get("field_order", "fragments")
        if field_order not in FIELD_ORDERS:
            raise ProfileError(f"{path}: 'field_order' must be one of {', '.join(FIELD_ORDERS)}")
        return Pack(
            name,
            tuple(fragments),
            tuple(rdf_profiles),
            frozenset(redefines),
            conformance,
            frozenset(keep_extras),
            series_schema,
            overrides,
            field_order,
        )

    def conformance(self, pack):
        """The mandatory properties per access layer of ``pack``, or None when it declares none."""
        if not pack.conformance:
            return None
        path = (self.root / pack.conformance).resolve()
        if self.root.resolve() not in path.parents:
            raise ProfileError(f"pack '{pack.name}': conformance file {pack.conformance!r} is outside {self.root}")
        try:
            rules = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as error:
            raise ProfileError(f"cannot read the conformance file of pack '{pack.name}' ({path}): {error}") from error
        _check_conformance_rules(path, rules)
        return rules

    def fragment(self, name):
        if name not in self._fragments:
            _check_name("fragment", name)
            path = self.root / "fragments" / f"{name}.yaml"
            if not path.is_file():
                raise ProfileError(f"fragment '{name}' not found: {path}")
            fragment = self._load(path)
            if not isinstance(fragment, dict):
                raise ProfileError(f"{path}: a fragment must be a mapping")
            self._fragments[name] = self._resolve_snippets(fragment, path)
        return self._fragments[name]

    def snippet(self, name):
        if name not in self._snippets:
            _check_name("snippet", name)
            path = self.root / "snippets" / f"{name}.yaml"
            if not path.is_file():
                raise ProfileError(f"snippet '{name}' not found: {path}")
            self._snippets[name] = self._load(path)
        return self._snippets[name]

    def _resolve_snippets(self, node, path):
        if isinstance(node, _SnippetRef):
            snippet = copy.deepcopy(self.snippet(node.name))
            if _contains_snippet_ref(snippet):
                raise ProfileError(f"snippet '{node.name}' may not reference other snippets ({path})")
            return snippet
        if isinstance(node, dict):
            return {key: self._resolve_snippets(value, path) for key, value in node.items()}
        if isinstance(node, list):
            return [self._resolve_snippets(item, path) for item in node]
        return node

    @staticmethod
    def _load(path):
        try:
            return yaml.load(path.read_text(encoding="utf-8"), Loader=_PackLoader)
        except (OSError, yaml.YAMLError) as error:
            raise ProfileError(f"cannot read {path}: {error}") from error


def _check_conformance_rules(path, rules):
    """Raise a ProfileError unless ``rules`` has the layers, and optionally the classes, conformance.py reads."""
    layers = rules.get("layers") if isinstance(rules, dict) else None
    if not isinstance(layers, dict) or set(layers) != set(ACCESS_LAYERS):
        raise ProfileError(f"{path}: expected 'layers' with exactly {', '.join(ACCESS_LAYERS)}")
    for layer, body in layers.items():
        if not _is_rule_list(body.get("mandatory") if isinstance(body, dict) else None):
            raise ProfileError(f"{path}: layer {layer} needs a 'mandatory' list of {{property, fields}}")
    classes = rules.get("classes", {})
    if not isinstance(classes, dict) or set(classes) - set(CLASS_KINDS):
        raise ProfileError(f"{path}: 'classes' may only name {', '.join(CLASS_KINDS)}")
    for kind, body in classes.items():
        if not _is_rule_list(body.get("mandatory") if isinstance(body, dict) else None):
            raise ProfileError(f"{path}: class {kind} needs a 'mandatory' list of {{property, fields}}")


def _is_rule_list(mandatory):
    """Whether ``mandatory`` is a list of ``{property, fields}`` rules."""
    return isinstance(mandatory, list) and all(
        isinstance(rule, dict)
        and isinstance(rule.get("property"), str)
        and isinstance(rule.get("fields"), list)
        and rule["fields"]
        for rule in mandatory
    )


def _check_name(kind, name):
    # Names reach the filesystem, and profile names come from the environment.
    if not isinstance(name, str) or not _NAME.match(name):
        raise ProfileError(f"invalid {kind} name {name!r}: use lowercase letters, digits and underscores")


def _string_list(path, manifest, key, required):
    value = manifest.get(key)
    if value is None:
        if required:
            raise ProfileError(f"{path}: '{key}' is required")
        return []
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise ProfileError(f"{path}: '{key}' must be a list of strings")
    if required and not value:
        raise ProfileError(f"{path}: '{key}' may not be empty")
    return value


def _contains_snippet_ref(node):
    if isinstance(node, _SnippetRef):
        return True
    if isinstance(node, dict):
        return any(_contains_snippet_ref(value) for value in node.values())
    if isinstance(node, list):
        return any(_contains_snippet_ref(item) for item in node)
    return False


# --- Configuration (environment) ---------------------------------------------------


def parse_profiles(raw):
    """Pack names from ``GDI_METADATA_PROFILES``: separated by commas and/or whitespace.

    Unset or empty means the default pack, because Compose passes empty strings for
    unset variables. Separators only, and duplicate names, are errors.
    """
    if raw is None or not raw.strip():
        log.info("%s is unset or empty: using the default profile '%s'", ENV_PROFILES, DEFAULT_PROFILE)
        return [DEFAULT_PROFILE]
    names = [name for name in _SEPARATORS.split(raw.strip()) if name]
    if not names:
        raise ProfileError(f"{ENV_PROFILES}={raw!r} contains no profile name")
    duplicates = sorted({name for name in names if names.count(name) > 1})
    if duplicates:
        raise ProfileError(f"{ENV_PROFILES} lists a profile twice: {', '.join(duplicates)}")
    return names


def parse_form_languages(raw, setting=ENV_FORM_LANGUAGES):
    """The languages of the edit form, in order; None when unset or empty (the schemas keep their own list).

    ``setting`` names where ``raw`` came from, for the error messages.
    """
    if raw is None or not raw.strip():
        return None
    languages = [token for token in _SEPARATORS.split(raw.strip()) if token]
    invalid = [token for token in languages if not _LANGUAGE_CODE.match(token)]
    if invalid:
        raise ProfileError(f"{setting} has invalid language codes: {', '.join(invalid)}")
    duplicates = [token for token in _unique(languages) if languages.count(token) > 1]
    if duplicates:
        raise ProfileError(f"{setting} lists a language twice: {', '.join(duplicates)}")
    return languages


def form_languages_setting(environ):
    """``(raw value, setting name)`` the form languages come from: their own setting, else the locales offered."""
    for name in (ENV_FORM_LANGUAGES, ENV_LOCALES_OFFERED):
        raw = environ.get(name)
        if raw is not None and raw.strip():
            return raw, name
    return None, ENV_FORM_LANGUAGES


def parse_main_profile(raw, profiles):
    """The main profile from ``GDI_METADATA_MAIN_PROFILE``; the first enabled one when unset."""
    main = (raw or "").strip()
    if not main:
        log.info("%s is unset or empty: the main profile is '%s'", ENV_MAIN_PROFILE, profiles[0])
        return profiles[0]
    if main not in profiles:
        raise ProfileError(
            f"{ENV_MAIN_PROFILE}='{main}' is not an enabled profile. Enabled: {', '.join(profiles)}"
        )
    return main


# --- Merging -----------------------------------------------------------------------


@dataclasses.dataclass
class Build:
    profiles: list
    schema: dict
    # "section.field_name" (or a header key) -> the enabled packs that define it
    fields: dict
    # one entry per definition that lost to a higher-precedence pack
    conflicts: list
    rdf_profiles: dict
    # the schema of the dataset series of the first enabled pack that has one
    series_schema: typing.Optional[str] = None
    # The form languages from the environment, when set, and the copy of the series schema written for them
    form_languages: typing.Optional[list] = None
    series_file: typing.Optional[Path] = None


@dataclasses.dataclass
class _Definition:
    pack: str
    fragment: str
    value: object


def build_schema(profiles, root=PACK_ROOT):
    """Merge the fragments of ``profiles`` (in precedence order, first wins) into one schema.

    Field order is first occurrence along the packs and their fragments, because it is
    the form order. A field defined identically everywhere is merged. A field defined
    differently needs a ``redefines`` entry in one of the packs defining it, and the
    earliest pack wins; without one the build fails.
    """
    registry = Registry(root)
    packs = [registry.pack(name) for name in profiles]

    definitions = {}  # key -> [_Definition] in precedence order
    order = []  # keys in first-occurrence order; a key is "<section>.<field_name>" or a header key
    shape = []  # top-level keys in first-occurrence order
    for pack in packs:
        defined_by_pack = set()
        for fragment_name in pack.fragments:
            fragment = registry.fragment(fragment_name)
            for top_key, value in fragment.items():
                if top_key not in shape:
                    shape.append(top_key)
                if top_key in FIELD_SECTIONS:
                    entries = [
                        (f"{top_key}.{_field_name(fragment_name, top_key, field)}", field)
                        for field in value or []
                    ]
                else:
                    entries = [(top_key, value)]
                for key, entry in entries:
                    if key in pack.overrides:
                        entry = {k: v for k, v in {**entry, **pack.overrides[key]}.items() if v is not None}
                    if key not in definitions:
                        definitions[key] = []
                        order.append(key)
                    definitions[key].append(_Definition(pack.name, fragment_name, entry))
                    defined_by_pack.add(key)
        for key in sorted(pack.redefines - defined_by_pack):
            raise ProfileError(f"pack '{pack.name}' redefines '{key}' but does not define it")
        for key in sorted(set(pack.overrides) - defined_by_pack):
            raise ProfileError(f"pack '{pack.name}' overrides '{key}' but does not define it")
        for name in sorted(pack.keep_extras):
            if f"dataset_fields.{name}" not in defined_by_pack:
                raise ProfileError(f"pack '{pack.name}' keeps the extra '{name}' but does not define it as a dataset field")

    by_name = {pack.name: pack for pack in packs}
    conflicts = []
    resolved = {}
    for key in order:
        resolved[key], conflict = _resolve(key, definitions[key], by_name)
        if conflict:
            conflicts.append(conflict)
            log.warning(
                "'%s' is defined differently by %s; '%s' wins by precedence (differs in: %s)",
                key,
                ", ".join([conflict["winner"], *conflict["losers"]]),
                conflict["winner"],
                ", ".join(conflict["differing_keys"]),
            )

    schema = {}
    for top_key in shape:
        if top_key in FIELD_SECTIONS:
            fields = [resolved[key] for key in order if key.startswith(f"{top_key}.")]
            if packs and packs[0].field_order == "alphabetical":
                fields = sort_alphabetically(fields, top_key)
            schema[top_key] = fields
        else:
            schema[top_key] = resolved[top_key]

    return Build(
        profiles=list(profiles),
        schema=schema,
        fields={key: _unique(d.pack for d in definitions[key]) for key in order},
        conflicts=conflicts,
        rdf_profiles={pack.name: list(pack.rdf_profiles) for pack in packs},
        series_schema=next((pack.series_schema for pack in packs if pack.series_schema), None),
    )


def _label_text(field):
    label = field.get("label")
    if isinstance(label, dict):
        label = label.get("en") or next(iter(label.values()), None)
    return str(label or field.get("field_name", ""))


def sort_alphabetically(fields, section):
    """``fields`` by label, ignoring case, with the title and the description of the section first."""
    leading = LEADING_FIELDS.get(section, ())

    def key(field):
        name = field.get("field_name", "")
        rank = leading.index(name) if name in leading else len(leading)
        return (rank, _label_text(field).lower(), name)

    return sorted(fields, key=key)


def _field_name(fragment, section, field):
    if not isinstance(field, dict) or not isinstance(field.get("field_name"), str):
        raise ProfileError(f"fragment '{fragment}': every entry of {section} needs a 'field_name'")
    return field["field_name"]


def _resolve(key, definitions, packs):
    first = definitions[0]
    if len({_canonical(d.value) for d in definitions}) == 1:
        return first.value, None

    clash = _difference_within_a_pack(definitions)
    if clash:
        raise ProfileError(
            f"'{key}' is defined differently in fragments '{clash[0].fragment}' and "
            f"'{clash[1].fragment}' of pack '{clash[0].pack}'; a pack may define a field once"
        )

    involved = _unique(d.pack for d in definitions)
    differing = sorted(
        {
            name
            for d in definitions[1:]
            if _canonical(d.value) != _canonical(first.value)
            for name in _differing_keys(first.value, d.value)
        }
    )
    if not any(key in packs[name].redefines for name in involved):
        raise ProfileError(
            f"'{key}' is defined differently by packs {', '.join(involved)} (differs in: {', '.join(differing)}). "
            f"Add it to 'redefines' of one of them to let the order of {ENV_PROFILES} decide."
        )
    losers = [name for name in involved if name != first.pack]
    return first.value, {"field": key, "winner": first.pack, "losers": losers, "differing_keys": differing}


def _difference_within_a_pack(definitions):
    for index, left in enumerate(definitions):
        for right in definitions[index + 1 :]:
            if left.pack == right.pack and _canonical(left.value) != _canonical(right.value):
                return left, right
    return None


def _differing_keys(left, right):
    if isinstance(left, dict) and isinstance(right, dict):
        return [k for k in {*left, *right} if _canonical(left.get(k)) != _canonical(right.get(k))]
    return ["<value>"]


def _canonical(value):
    # JSON, not ==, so that true and 1 stay different.
    return json.dumps(value, sort_keys=True, default=repr)


def _unique(items):
    return list(dict.fromkeys(items))


def retired_fields(enabled, root=PACK_ROOT):
    """The fields that only packs outside ``enabled`` define, for the prune command.

    Returns ``{"dataset_fields": {field: [pack, ...]}, "resource_fields": {...}}``. A field that
    any enabled pack defines is not retired, however many retired packs also define it. A
    pack's ``keep_extras`` are left out: shared RDF code keeps those as free extras in every
    profile, so their values are not orphaned when the pack goes.
    """
    registry = Registry(root)
    enabled_fields = set(build_schema(list(enabled), root).fields)
    retired = {section: {} for section in FIELD_SECTIONS}
    for name in registry.pack_names():
        if name in enabled:
            continue
        pack = registry.pack(name)
        for key in build_schema([name], root).fields:
            section, _, field = key.partition(".")
            if section not in FIELD_SECTIONS or key in enabled_fields:
                continue
            if section == "dataset_fields" and field in pack.keep_extras:
                continue
            retired[section].setdefault(field, []).append(name)
    return retired


# --- Output ------------------------------------------------------------------------


def render_schema(schema, header=""):
    body = yaml.dump(
        schema,
        Dumper=_NoAliasDumper,
        sort_keys=False,
        allow_unicode=True,
        default_flow_style=False,
        width=float("inf"),
    )
    return f"{header}{body}"


def config_options(build, main, schema_path):
    """The CKAN config options that tie the deployment to the generated schema."""
    options = [
        (OPTION_PROFILES, " ".join(build.profiles)),
        (OPTION_MAIN_PROFILE, main),
    ]
    for name in build.profiles:
        options.append(
            (f"ckanext.dcat.metadata_profiles.{name}.rdf_profiles", " ".join(build.rdf_profiles[name]))
        )
    # The existing key, so every code path that reads it keeps working unchanged.
    options.append(("ckanext.dcat.rdf.profiles", " ".join(build.rdf_profiles[main])))
    static = [build.series_schema] if build.series_schema else list(STATIC_SCHEMAS)
    if build.series_file:  # a copy of it with the form languages of the environment
        static = [Path(build.series_file).resolve().as_uri()]
    options.append(("scheming.dataset_schemas", " ".join([Path(schema_path).resolve().as_uri(), *static])))
    options.append(("scheming.presets", " ".join(SCHEMING_PRESETS)))
    return [f"{key} = {value}" for key, value in options]


def check_rdf_profiles(build, installed):
    """Fail at start, not on the first request, when a pack names an RDF profile that is not installed."""
    for name in build.profiles:
        missing = [profile for profile in build.rdf_profiles[name] if profile not in installed]
        if missing:
            raise ProfileError(
                f"profile '{name}' needs RDF profiles that are not installed: {', '.join(missing)} "
                f"(entry point group {RDF_PROFILE_ENTRY_POINT_GROUP})"
            )


def installed_rdf_profiles():
    from importlib.metadata import entry_points

    return {entry_point.name for entry_point in entry_points(group=RDF_PROFILE_ENTRY_POINT_GROUP)}


def write_outputs(build, main, output_dir):
    """Write ``dataset.yaml`` and ``provenance.json``. Deterministic: a rerun is byte-identical."""
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    os.chmod(output_dir, 0o755)  # the CKAN user reads what root writes

    header = (
        "# GENERATED by ckanext.gdi_userportal.profile_packs.generator. Do not edit.\n"
        f"# profiles (precedence order): {' '.join(build.profiles)}\n"
        f"# main profile: {main}\n\n"
    )
    provenance = {
        "profiles": build.profiles,
        "main": main,
        "fields": build.fields,
        "conflicts": build.conflicts,
    }
    if build.form_languages:
        provenance["form_languages"] = build.form_languages
        build.series_file = _write_series_copy(build, output_dir, header)
    else:  # a copy left by an earlier start with form languages is not used any more
        (output_dir / SERIES_FILENAME).unlink(missing_ok=True)
    schema_path = output_dir / SCHEMA_FILENAME
    _write_atomically(schema_path, render_schema(build.schema, header))
    _write_atomically(output_dir / PROVENANCE_FILENAME, json.dumps(provenance, indent=2) + "\n")
    return schema_path


def _series_schema_file(reference):
    module, _, relative = reference.partition(":")
    if module == "ckanext.gdi_userportal":
        return PACK_ROOT.parent / relative
    spec = importlib.util.find_spec(module)
    if spec is None or not spec.submodule_search_locations:
        raise ProfileError(f"cannot find the series schema {reference}")
    return Path(next(iter(spec.submodule_search_locations))) / relative


def _write_series_copy(build, output_dir, header):
    """The series schema of the enabled packs, with the form languages of the environment."""
    reference = build.series_schema or STATIC_SCHEMAS[0]
    series = yaml.safe_load(_series_schema_file(reference).read_text(encoding="utf-8"))
    series["form_languages"] = list(build.form_languages)
    path = output_dir / SERIES_FILENAME
    _write_atomically(path, render_schema(series, header))
    return path


def _write_atomically(path, text):
    # A crash must never leave a half-written schema for the next start to load.
    handle, temporary = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.")
    try:
        with os.fdopen(handle, "w", encoding="utf-8") as stream:
            stream.write(text)
        os.chmod(temporary, 0o644)
        os.replace(temporary, path)
    except BaseException:
        if os.path.exists(temporary):
            os.unlink(temporary)
        raise


# --- Command line ------------------------------------------------------------------


def generate(
    raw_profiles,
    raw_main,
    output_dir,
    root=PACK_ROOT,
    installed=None,
    raw_form_languages=None,
    locale_default=None,
    form_languages_from=ENV_FORM_LANGUAGES,
):
    """The whole start-up step. ``installed`` (RDF profile names) enables the entry point check."""
    profiles = parse_profiles(raw_profiles)
    build = build_schema(profiles, root)  # first: an unknown pack is the root cause of a main profile mismatch
    main = parse_main_profile(raw_main, profiles)
    languages = parse_form_languages(raw_form_languages, form_languages_from)
    if languages:
        build.form_languages = languages
        build.schema["form_languages"] = languages
        if locale_default and locale_default != languages[0]:
            log.warning(
                "%s is '%s' but the first form language is '%s': the plain title and description, and the "
                "fallback of a text, use '%s'; the form lists '%s' first",
                ENV_LOCALE_DEFAULT, locale_default, languages[0], locale_default, languages[0],
            )
    if installed is not None:
        check_rdf_profiles(build, installed)
    schema_path = write_outputs(build, main, output_dir)
    log.info("generated %s for profiles: %s (main: %s)", schema_path, " ".join(profiles), main)
    return config_options(build, main, schema_path)


def main(argv=None, environ=None):
    environ = os.environ if environ is None else environ
    env_languages, env_languages_name = form_languages_setting(environ)
    parser = argparse.ArgumentParser(description=(__doc__ or "").split("\n\n")[0])
    parser.add_argument("--output-dir", required=True, help="where dataset.yaml and provenance.json are written")
    parser.add_argument("--profiles", default=environ.get(ENV_PROFILES), help=f"default: ${ENV_PROFILES}")
    parser.add_argument(
        "--main-profile", default=environ.get(ENV_MAIN_PROFILE), help=f"default: ${ENV_MAIN_PROFILE}"
    )
    parser.add_argument(
        "--form-languages",
        default=env_languages,
        help=(
            f"the languages of the edit form, in order (default: ${ENV_FORM_LANGUAGES}, else "
            f"${ENV_LOCALES_OFFERED}, else the schemas' own)"
        ),
    )
    parser.add_argument(
        "--skip-entry-point-check",
        action="store_true",
        help="do not check that the RDF profiles of the packs are installed",
    )
    args = parser.parse_args(argv)

    logging.basicConfig(
        stream=sys.stderr, level=logging.INFO, format="[metadata-profiles] %(levelname)s %(message)s"
    )
    try:
        installed = None if args.skip_entry_point_check else installed_rdf_profiles()
        options = generate(
            args.profiles,
            args.main_profile,
            args.output_dir,
            installed=installed,
            raw_form_languages=args.form_languages,
            form_languages_from=env_languages_name if args.form_languages == env_languages else "--form-languages",
            locale_default=environ.get(ENV_LOCALE_DEFAULT),
        )
    except ProfileError as error:
        print(f"[metadata-profiles] ERROR {error}", file=sys.stderr)
        return 1
    print("\n".join(options))
    return 0


if __name__ == "__main__":
    sys.exit(main())
