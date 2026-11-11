<!--
SPDX-FileCopyrightText: 2026 Stichting Health-RI

SPDX-License-Identifier: Apache-2.0
-->

# Metadata profile packs

One CKAN deployment can load several metadata profiles ("packs"), chosen at container start
(ADR 0001) with `GDI_METADATA_PROFILES`, `GDI_METADATA_MAIN_PROFILE` and `GDI_METADATA_FORM_LANGUAGES`;
the variables and examples are in `docs/metadata-profiles.md` of `gdi-userportal-ckan-docker`. The
generator merges the schema fragments of the enabled packs into one scheming `dataset` schema, because
ckanext-scheming cannot compose schemas at runtime. Unknown packs, duplicate names, a main profile that is not enabled, and undeclared conflicts stop
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

**The order matters for the fields R8 defines differently.** R8 defines `contact`, `spatial_coverage`, `publisher`,
`creator`, `qualified_attribution`, `was_generated_by`, `hdab`, `qualified_relation` and the resource field
`access_services` differently: a `vcard:Kind` contact point with an email and one contact page
(`vcard:hasURL` is at most one) and nothing else, a location that is an IRI with a geometry, a
bounding box and a centroid (no label), plain agents with a name and a type (the health agents of a
dataset add the `cv:ContactPoint`, whose email, contact page and telephone are lists because R8 allows
`0..n` of each, with the opening hours; the publisher a description), an activity with a label and a
type, a relationship with one or more relations and roles, and the properties of `dcat:DataService` only. It also calls `spatial_coverage` "Geographical coverage" and
`spatial_resolution_in_meters` "Spatial resolution" (the IRI keeps the unit), and has at most one
retention period. A distribution carries the names R8 gives its properties: title, compression format,
packaging format, byte size, licence and linked schemas (the labels differ from `gdi_current`, so
these resource fields are redefined too). Its checksum is an entity, as in R8 (`checksum` with an
`algorithm`, one of the SPDX members, and a lower case hexadecimal `checksum_value`, checked by the
validator `gdi_hex_binary`), where `gdi_current` has the two plain fields `hash` and `hash_algorithm`;
each pack has its own fragment for it (`r8_checksum`, `gdi_resource_checksum`). The availability is one
concept of the EU planned-availability vocabulary (a choice), where `gdi_current` takes free text. The pack declares them with `redefines`, so
with both packs enabled the pack listed first decides. With `gdi_current` first they keep their
`gdi_current` subfields, and a parsed value for a subfield that is missing is dropped (a value for a
subfield that holds one value keeps the first, with a warning), so the dataset stays valid. List
`healthdcat_r8` first to get the R8 versions. The main profile is set apart from the order, so this
does not change which mapping an export uses by default.

R8 fields that allow several values where `gdi_current` holds one and that are lists in the R8 pack:
the relations and roles of `qualified_relation`, the roles of `qualified_attribution`, the landing
page (`url`) and the type (`dcat_type`) of a dataset, and the access URL (`access_url`) and download
URL (`download_url`) of a distribution. The rights of a distribution are a list of statements, each
with an optional IRI and a label per language (`rights` with the subfields `uri` and
`label_translated`; the pack removes the `fluent_markdown` preset of `gdi_current` with a `null` in
its `overrides`). The title, description and endpoint description of a data service
(`access_services`) hold a text per language in the R8 pack (`fluent_text`; the subfield values are
language maps). Consumers that read one value of each (the Discovery Service) have to handle lists
before an R8-first deployment serves them; see "Known limits" in `docs/metadata-profiles.md` of
`gdi-userportal-ckan-docker`. Solr keeps one value in `url` and `dcat_type` (changing
`multiValued` needs a reindex): `before_dataset_index` puts the first value there, and every type in
`vocab_dcat_type`. The identifier stays single-valued: the R8 profile keeps the first value and logs a
warning when it drops others (ADR 0001, Q3).

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
overrides:                 # optional: keys that replace those of a field this pack defines, for this pack only
  dataset_fields.retention_period: {repeating_once: true}
field_order: fragments     # optional: fragments (the default) or alphabetical, see below
```

`overrides` is for a label or a cardinality that differs, so that a shared fragment does not need a
copy; a key set to `null` is removed from the field (a preset that the pack replaces by subfields of its
own). The overridden field still needs a `redefines` entry when another pack defines it too.

`field_order: alphabetical` orders the `dataset_fields` and the `resource_fields` of the generated
schema by label (a label per language is read in English, ignoring case), with the title and the
description first (`title_translated`, `notes_translated` and `name_translated`,
`description_translated`). It is the order of the edit form and of the display of a dataset and of a
distribution. Without it the order is that of the fragments. With several packs enabled the pack listed
first decides. Both `healthdcat_r8` and `gdi_current` are alphabetical; the static series schemas,
`dataset_series_r8.yaml` and `dataset_series_multilingual.yaml`, are kept in the same order by hand (a
test checks them). The subfields of a field keep their own order, which follows the model, except those of
a data service (`access_services`): they are in the same alphabetical order, title and description first,
kept by hand in `r8_access_services.yaml` and `health_access_services.yaml` and checked by a test.
`scheming/schemas/dataset_multilingual.yaml` keeps the original field order; the acceptance test compares
it with `gdi_current` field by field, by name.

**Dataset series.** A series is not generated from fragments: each pack that has a model for it
ships a static schema and names it with `series_schema`. With several packs enabled the one listed
first decides, as for the redefined fields (a pack without one is skipped). `gdi_current` keeps
`dataset_series_multilingual.yaml`, `healthdcat_r8` has `dataset_series_r8.yaml` with the
properties of `dcat:DatasetSeries` only: no ordering of the members (`series_order_*`, which only
drive the previous and next links of the series extension), no legacy publisher fields and one
contact page. The prune command does not look at series fields.

**Display keys.** Scheming passes keys it does not know through, and the display templates of this
extension use some on a subfield: `display_group` shows the subfields with the same value together
under that heading (the contact point of an agent: the email and URL in `gdi_current`, more in R8); `display_replaces: <subfield>` makes the
subfield take the row of that other one when it has a value, under its `display_label` (one or more
names per language replace the single name). A field with `repeating_once` is shown without a number,
and nested lists (variables, tables, columns) are indented.

**Hiding.** Datasets of a harvest source whose `metadata_profile` is not enabled are hidden
(`profile_visibility.py`); see "Datasets of a profile that is not enabled" in `docs/metadata-profiles.md`
of `gdi-userportal-ckan-docker`.

**Empty properties.** A dataset page and a distribution page list what has a value. With the option
`ckanext.gdi_userportal.show_empty_properties = true` (the environment variable
`CKANEXT__GDI_USERPORTAL__SHOW_EMPTY_PROPERTIES=true`) they list every property the schema defines, with
a dash for those without a value, to see what the schema, the edit form and a harvest can hold. It is
off by default. The generated schema holds the fields of every enabled profile, so a dataset gets a dash
only for the fields of the profile of its harvest source (`conformance_service.empty_property_scope`, from
the fields each pack defines); a dataset no source says anything about gets all of them, and a field with a
value is always shown.

**Language fallback.** The edit form stores an empty value for a form language left blank
(`{"en": "Title", "nl": ""}`), and scheming and CKAN only fall back to another language when the key
is missing. `after_dataset_show` (`languages.py`) therefore drops the empty languages of the fluent
fields of a dataset, its resources and their nested subfields from what `package_show` returns, so a
page in Dutch shows the English title, description, keywords, population coverage and version notes
when there is no Dutch one. The stored value is unchanged, the edit form still offers every language,
and an empty core field (`title`, `notes`) takes the first language that has a value.

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
access layer (`evaluate`), and which a distribution or a dataset series satisfies (`evaluate_class`, no
layer). `conformance_service.py` (one level up) wraps both for the API action
`gdi_metadata_profile_conformance`, the sysadmin report action `gdi_metadata_profile_conformance_report`
and the `profiles conformance` command, and for the page helpers `h.gdi_profile_conformance` (dataset and
series pages, `package/read.html`, and the lists, `snippets/package_item.html`) and
`h.gdi_resource_conformance` (the distribution list, `package/snippets/resource_item.html`, and the
distribution page). The harvest-log warning of ckanext-fairdatapoint calls the action. Everything is computed
on demand; nothing is stored and the Solr schema and the index are not involved. A pack with no
`conformance` file has no mandatory properties.

A record is checked against the profile it comes from: the `metadata_profile` of its harvest source, the
main profile when the source names none, every enabled profile when no source created it
(`applicable_profiles`; the source lookup is `profile_visibility.source_profiles`). A sample
(`adms:sample`) and an analytics distribution (`healthdcatap:analytics`) are stored as resources and are
distributions: they are checked like any other and labelled by `resource_kind`.

The file of `healthdcat_r8` is **generated** from R8's cardinality rules, never edited by hand:

```
conformance/healthdcat_r8_fields.yaml     R8 property label -> the CKAN fields that carry it (hand-written),
                                          and `classes`: what R8's SHACL shapes make mandatory on a
                                          distribution and a dataset series (applicable legislation)
conformance/healthdcat_r8.json            generated: the properties that are Mandatory per layer, and `classes`
```

R8's cardinality rules cover the dataset only. The distribution and series rules come from
`:Distribution_Shape` and `:DatasetSeries_Shape` of the R8 SHACL files, which are identical in the public,
restricted and non-public shapes, so they have no layer. The build copies them as they are.

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

## Solr schema

`solr/schema.xml` is written by hand: field types, CKAN's own fields and some of the fields the plugin
builds while indexing (agents, contact point, `vocab_*`). The dataset fields of the enabled profiles are
not in it. Solr gives a field it does not know the catch-all `*` (not stored, **single valued**), so a
profile field with several values fails the import ("multiple values encountered for non
multiValued field"). `solr_schema.py` closes that:

- `derive_fields` makes a Solr field of every dataset field that `schema.xml` does not declare (and no
  dynamic field other than `*` covers). Its type follows from the validators of the scheming field
  (`int_validator` is a `long`, `boolean_validator` a `boolean`, anything else a `string`: a partial
  date such as `2020` is not a Solr date, and a language map is stored as JSON text). It is multi valued
  when the scheming field is a list (repeating subfields, `multiple_text`/`multiple_select`/
  `multiple_checkbox`, `scheming_multiple_choice`/`scheming_multiple_text`, `dataset_series_in_series`,
  `series_validator`), indexed and not stored. A `solr` key on the field overrides each of these:

  ```yaml
  - field_name: issued
    solr: {type: date, index: true, store: false, multiple: false}   # every key is optional
  ```

  *Indexed* means Solr can search, filter, facet and sort on the field. *Stored* means Solr can return
  the original value in a query; CKAN does not need that, it serves a dataset from the JSON in
  `validated_data_dict`. `type` must be a field type of `schema.xml`; `check` reports one that is not.
- `check` (the drift test, `tests/profile_packs/test_solr_schema.py`, for every pack and pack pair)
  fails when a list field would land in a single valued Solr field, when a `flatten` key (below) names a
  subfield the field does not have, and when a Solr field the indexing fills is declared single valued in
  `schema.xml`. A field with `solr: {multiple: false}` is exempt: the indexing keeps one value of the list.
  Fix a failure by making the field `multiValued` in `schema.xml`, or by marking the field `multiple: false`.

### What the indexing writes: the `solr` key

CKAN hands the indexer a dataset whose list fields are JSON text and whose repeating fields are lists of
objects; scheming turns those into one `extras_<field>__<subfield>` text field each, which Solr can search
but neither filter nor facet on. `before_dataset_index` therefore writes plain multi valued Solr fields of its
own, and which ones is decided by the `solr` key of the fields in the schema, not by a list of names in the
plugin (`indexing.py`; the schema is read through `schema_fields.py`):

```yaml
- field_name: spatial_coverage
  solr: {flatten: [uri]}                  # -> spatial_coverage_uri: one value per location
- field_name: contact
  solr: {prefix: contact_point, flatten: [uri, name, email]}   # -> contact_point_uri, contact_point_name, ...
- field_name: qualified_attribution
  solr: {prefix: vocab_qualified_attribution, flatten: [role, agent.name]}   # a dot reaches into a subfield
- field_name: theme
  solr: {text: false}                     # no extras_theme copy in the free text
- field_name: dcat_type
  solr: {multiple: false, all_values: vocab_dcat_type, text: false}   # the first value, and all of them
```

- `flatten` lists the subfields of a repeating field that get a Solr field each, `<prefix>_<subfield>`
  (`prefix` is the name of the field unless it says otherwise; a path with a dot is joined with `_`). Only
  what is listed is indexed: a geometry or a language map is not a useful filter. `derive_fields` makes the
  Solr field (a multi valued string) when `schema.xml` does not declare it.
- `text: false` marks a field that is indexed under its own name: the `extras_<field>` copy that CKAN adds
  (and that Solr copies into the free-text field) is dropped, as it would only hold JSON text. On a
  repeating field it drops the list once it is flattened, so scheming makes no `extras_<field>__<subfield>`
  text of it either (those say `None` for every empty value).
- `multiple: false` (with the `type`, `index` and `store` keys of the section above) says the Solr field
  holds one value although the scheming field is a list, as for the landing page and the type of
  `healthdcat_r8`; the first value is kept and `all_values` names a second Solr field that gets all of them.
- A field that holds a list and has no repeating subfields has its JSON text decoded to a list. `decode:
  false` leaves it as it is, for a field that another plugin reads as text while indexing: this plugin runs
  before ckanext-dataset-series, which does `json.loads` on `in_series`.

A pack states these next to the field it defines, so a pack that redefines a field (see `redefines`) states
them again; the pack listed first wins as for any other key. The series schemas carry them too. A field
without a mark is indexed as before: under its own name when it has a value, and as `extras_*` text.
- `sync` runs from the start scripts after the generator: it compares `schema.xml` plus the derived
  fields with the running core and applies the difference through the Solr Schema API (`add-field`,
  `replace-field`, dynamic and copy fields). It never deletes a field and never stops CKAN when Solr
  does not answer. A core is created once from the Solr image and lives in a volume, so a changed
  `schema.xml` or a new profile would never reach an existing core without it.

```
python3 -m ckanext.gdi_userportal.profile_packs.solr_schema sync --dataset-schema /srv/app/generated/dataset.yaml [--dry-run]
```

Documents indexed before a change keep their old index: reindex (`ckan search-index rebuild`) after the
sync reports changes. A field type that the core lacks is reported, not added: recreate the core.
The fields that `schema.xml` declares by hand (`publisher_name`, `contact_point_*`, ...) keep their own settings; a new `flatten` key needs no line in `schema.xml`.

## What the API shows: the `translate` and `agent` keys

`package_show`, `package_search` and the other actions of the plugin show the codes of a controlled
vocabulary with their label, and give every agent one shape. Which fields that concerns is decided by the
schema, not by a list of names in the plugin (`logic/action/translation_utils.py`; the schema is read through
`schema_access.py` and `schema_fields.py`):

```yaml
- field_name: theme
  translate: true                          # "http://.../data-theme/HEAL" -> {name, display_name, count}
- field_name: was_generated_by
  repeating_subfields:
    - field_name: type
      translate: true                      # a subfield of a repeating field
    - field_name: dct_type
      translate: {label_in: label}         # the value stays, its label goes to the subfield `label`
    - field_name: wasAssociatedWith
      agent: true                          # an agent: its identifier is always a list
```

- `translate: true` shows the value of a field (a list: each value) as `{name, display_name, count}`, with the
  label in the language of the request, English when there is none. A repeating field needs no mark of its
  own: it is walked when one of its subfields has one. `translate: {label_in: <subfield>}` leaves the value
  and writes its label to that sibling subfield, as the discovery API wants for `dct_type`.
- `agent: true` says the field holds organisations or persons; each of them gets an `identifier` list, an empty
  one when it has none, whatever the way it was created. It nests: an agent can hold agents.
- The subfields every agent has (`type`, `publisher_type`, `country`) are marked in the agent snippets, so a
  pack that uses a snippet has them translated; `hdab_*` snippets are not marked.
- The multilingual text fields (`fluent_markdown`, `fluent_text`: `provenance`, `version_notes`, the note of
  a publisher, ...) and every `<field>_translated` show the text of the requested language, then English,
  then any language. No mark is needed: they are found by their preset.
- The API answers in English and Dutch, and in every other language of `form_languages` (what the form offers,
  `GDI_METADATA_FORM_LANGUAGES`); a form limited to English does not take Dutch away.
- Only `type`, the CKAN core field that is not in the schema, is named in the plugin.

The terms that `package_show` looks up in `term_translation_show` are collected from the same marks, so a
new marked field needs no other change. A marked field the dataset has no value for is `null`
(`[]` for a repeating field of a distribution, `access_services`); a name that is not a field of the schema
is not made up.

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

## Empty values are not saved

The edit form posts an input for every language and subfield, and the RDF profiles fill every form language with
an empty text, so datasets used to be stored with `{"en": "", "nl": ""}`, `[]` and `""` as extras. A dataset is
saved without them now (`blank_values.py`, `logic/action/blank_values.py`):

- `package_create` and `package_update` are chained, so the form, the API, `package_patch` (it hands the merged
  dataset to `package_update`: a field set to `""` is dropped and so cleared) and every harvester go through it.
  The fields of the dataset schema (and of its resource fields) that end up as extras are looked at; the
  columns CKAN has itself (`title`, `notes`, `url`, ...) are not.
- A value is empty when it holds no text, item or language at any depth, as a list of rows that are all empty
  is. A flat map loses its empty languages (`{"en": "Title", "nl": ""}` is saved as `{"en": "Title"}`) and a list
  of texts its empty items. `0` and `false` are values.
- **A row of a repeating field is never changed from the inside**: the validation of nested subfields (a
  qualified attribution with an agent) fails for a row that lacks a key it had, and the dataset can then not be
  indexed. Such a field is saved as it came, or not at all when every row is empty.
- A required field that is empty is still reported by the validation, as missing. The code that reads a dataset
  has to cope with a field that is not there; the harvesters pad every form language on purpose, that stays.
- If dropping fails for any reason the dataset is saved as it came: a save is never stopped by this.

`ckan gdi-userportal clean-blank-values` does the same for what is stored already: a dry run that lists what
would be removed or rewritten, and with `--apply` (asks for confirmation unless `--yes`) removes it and reindexes
the datasets. It looks at `package_extra` and the extras of the resources, never at deleted datasets. Take a
database backup first.
