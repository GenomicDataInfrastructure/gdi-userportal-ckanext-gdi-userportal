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

## Packs

| Pack | Metadata model | RDF profile chain |
|---|---|---|
| `gdi_current` | The portal's original model | `fairdatapoint_dcat_ap euro_dcat_ap_nl` |
| `healthdcat_r8` | HealthDCAT-AP Release 8 | `euro_health_dcat_ap_r8` |

`healthdcat_r8` shares the neutral fields of `gdi_current` and adds `alternative_title`,
`related_resource`, `source`, `has_structured_data`, `variables`, `custodian` and
`hdab_coordinator`. `dataset_status` and `trusted_data_holder` stay `gdi_current` only: R8 has
no such property. `related_resource` and `source` reuse the key of the free extras that exist
today, so saved values become field values in place.

The R8 pack holds the properties of the R8 model and nothing else; what only `gdi_current` has
stays in `gdi_current`. That is the HealthDCAT-AP publisher note and type (on the dataset and on the
agents), the license of the dataset, the retention period of a distribution, the identifier and
country of an agent, and the extra subfields of the activity and of a data service. R8 types an
agent with `dct:type` (the `type` subfield) and writes the description of a publisher as
`dct:description`; that subfield keeps the key `publisher_note`, because field names are the same in
every profile, and is labelled "Description" in R8. In R8 the email and the contact page of a health
agent belong to its contact point, so the subfield `url` is labelled "Contact page".

**The order matters for seven fields.** R8 defines `contact`, `publisher`, `creator`,
`qualified_attribution`, `was_generated_by`, `hdab` and the resource field `access_services`
differently: a contact point with one contact page (`vcard:Kind` has at most one `vcard:hasURL`),
plain agents with a name and a type (the health agents of a dataset add the contact point with the
telephone and the opening hours, the publisher a description), an activity with a label and a type,
and the properties of `dcat:DataService` only. The pack declares them with `redefines`, so with both
packs enabled the pack listed first decides. With `gdi_current` first they keep their `gdi_current`
subfields, and a parsed value for a subfield that is missing is dropped, so the dataset stays valid.
List `healthdcat_r8` first to get the R8 versions. The main profile is set apart from the order, so
this does not change which mapping an export uses by default.

R8 fields that allow several values where `gdi_current` holds one (`identifier`, `dcat_type`,
the landing page, the access and download URL of a distribution, ...) stay single-valued. The
R8 profile keeps the first value and logs a warning when it drops others (ADR 0001, Q3).

The R8 variants of the agent snippets and of `access_services` are copies. The tests in
`test_healthdcat_r8_pack.py` check that each equals the `gdi_current` one plus what R8 adds and
minus what it leaves out.

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
conformance: conformance/<name>.json   # optional: mandatory properties per access layer (generated)
keep_extras: []            # optional: dataset fields that stay when this pack is retired (see Pruning)
series_schema: pkg:path/to/series.yaml   # optional: the static scheming schema of the dataset series
```

**Dataset series.** A series is not generated from fragments: each pack that has a model for it
ships a static schema and names it with `series_schema`. With several packs enabled the one listed
first decides, as for the redefined fields (a pack without one is skipped). `gdi_current` keeps
`dataset_series_multilingual.yaml`, `healthdcat_r8` has `dataset_series_r8.yaml` with the
properties of `dcat:DatasetSeries` only: no ordering of the members (`series_order_*`, which only
drive the previous and next links of the series extension), no legacy publisher fields and one
contact page. The prune command does not look at series fields.

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

## Conformance

`conformance.py` (standard library only) says which enabled packs a dataset satisfies at its
access layer; the API action `gdi_metadata_profile_conformance` and the harvest-log warning of
ckanext-fairdatapoint use it. A pack with no `conformance` file has no mandatory properties.

The file of `healthdcat_r8` is **generated** from R8's cardinality rules, never edited by hand:

```
conformance/healthdcat_r8_fields.yaml     R8 property label -> the CKAN fields that carry it (hand-written)
conformance/healthdcat_r8.json            generated: the properties that are Mandatory per layer
```

```
python3 profile_packs/conformance_build.py --rules path/to/healthdcat-cardinality-rules.json [--check]
```

The build fails when a mandatory property has no fields in the mapping, a mapped property is not
mandatory in any layer, or a rule contradicts itself. `--check` exits 1 when the committed file is
out of date; the host test `test_the_committed_file_is_what_the_real_rules_produce` does the same
when `HEALTHDCAT_RULES_JSON` points at the rules file. The generated file records the SHA-256 of
the rules it came from.

## Pruning

`generator.retired_fields(enabled)` lists the fields that only packs outside `enabled` define. The
command `ckan gdi-userportal profiles prune` (a dry run unless `--delete`) uses it to find the
extras to remove; see `prune.py`. A field a pack lists under `keep_extras` is never retired: use it
for a field whose key the shared RDF code also keeps as a free extra in every profile
(`related_resource` and `source` in `healthdcat_r8`).

## Running it

```
python3 -m ckanext.gdi_userportal.profile_packs.generator --output-dir /srv/app/generated
```

It writes `dataset.yaml` and `provenance.json` there and prints the CKAN config options to apply.
The start scripts feed those to `ckan config-tool`.

Tests need only PyYAML, SQLAlchemy and pytest, and run on the host:

```
uv run --no-project --with pyyaml --with sqlalchemy --with pytest python -I -m pytest ckanext/gdi_userportal/tests/profile_packs
```
