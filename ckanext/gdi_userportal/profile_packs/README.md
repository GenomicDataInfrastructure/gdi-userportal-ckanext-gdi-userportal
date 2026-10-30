<!--
SPDX-FileCopyrightText: 2026 Stichting Health-RI

SPDX-License-Identifier: Apache-2.0
-->

# Metadata profile packs

One CKAN deployment can load several metadata profiles ("packs"), chosen at container start
(ADR 0001). The generator merges the schema fragments of the enabled packs into one scheming
`dataset` schema, because ckanext-scheming cannot compose schemas at runtime.

| Variable | Meaning | Default |
|---|---|---|
| `GDI_METADATA_PROFILES` | Pack names, separated by commas and/or whitespace. The order is the precedence order: the first pack wins. | unset or empty: `gdi_current` |
| `GDI_METADATA_MAIN_PROFILE` | The deployment's main profile. Must be one of the enabled packs. | the first enabled pack |

Unknown packs, duplicate names, a main profile that is not enabled, and undeclared conflicts stop
the container from starting.

## Layout

```
profile_packs/
  generator.py             stdlib + PyYAML only; runs before prerun.py, and on the host in tests
  packs/<name>.yaml        manifest
  fragments/<name>.yaml    partial schema
  snippets/<name>.yaml     YAML reused by several fragments
```

**Pack manifest**

```yaml
name: gdi_current          # must equal the file name
fragments: [core, ...]     # the schema; order matters (see below)
rdf_profiles: [a, b]       # ckan.rdf.profiles entry points, in order
redefines: []              # "<section>.<field_name>" this pack defines differently from another pack
```

**Fragment**: header keys (`scheming_version`, `form_languages`, ...), `dataset_fields` and
`resource_fields`. Reuse a block with `!snippet <name>`; YAML anchors cannot span files.

## Merging

- Field order is the first occurrence along the enabled packs and their fragments, because it is the
  form order. A fragment is therefore a *contiguous* slice of the form, not a topic: a field that
  belongs to another profile and sits between two shared fields lives in a fragment of its own.
- A field defined identically by several packs is merged.
- A field defined differently needs a `redefines` entry in one of the packs defining it. The earlier
  pack in `GDI_METADATA_PROFILES` wins, and the resolution is logged and written to `provenance.json`.
- A field defined differently and not declared fails the build, naming the field, the packs and the
  keys that differ.
- `provenance.json` records which enabled packs define each field.

## Running it

```
python3 -m ckanext.gdi_userportal.profile_packs.generator --output-dir /srv/app/generated
```

It writes `dataset.yaml` and `provenance.json` there and prints the CKAN config options to apply.
The start scripts feed those to `ckan config-tool`.

Tests need only PyYAML and pytest, and run on the host:

```
uv run --no-project --with pyyaml --with pytest python -I -m pytest ckanext/gdi_userportal/tests/profile_packs
```
