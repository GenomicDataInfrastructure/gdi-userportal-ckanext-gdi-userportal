# SPDX-FileCopyrightText: 2026 Stichting Health-RI
#
# SPDX-License-Identifier: Apache-2.0

"""
Characterization tests: what the plugin does with real datasets, recorded before the indexing and the
translation were made to follow the generated schema.

``fixtures/index_and_api_corpus.json`` was recorded from a running stack with ``fixtures/capture_corpus.py``
(nothing is written to Solr or the database). For each dataset it holds

* what ``before_dataset_index`` received and returned, with the two lookups it makes (the series a dataset is in,
  the translations of the terms it indexes);
* what ``package_show`` returned, the terms the translation layer asks for, the translations it got back, and what
  ``replace_package`` made of the dataset in English and Dutch.

A change that moves any of this has to say so, with the reason, in ``expected_document`` or
``DELIBERATE_API_CHANGES``, as ``test_gdi_current_golden.py`` does for the schema.

What is not compared, because it does not reach Solr or does not mean anything to it:

* the order of a list of plain values (the plugin builds some of them from sets), and the white space around
  its values (the indexing strips what it flattens);
* a field with no value against a field that is not there (an empty list or an empty string);
* the repeating fields: scheming, which runs after this plugin, drops them from the document.
"""

import json
from copy import deepcopy
from pathlib import Path
from unittest.mock import patch

import pytest
import yaml
from ckan.plugins import toolkit

from ckanext.gdi_userportal.logic.action.translation_utils import (
    collect_values_to_translate,
    replace_package,
)
from ckanext.gdi_userportal.plugin import GdiUserPortalPlugin
from ckanext.gdi_userportal.profile_packs import generator

# The profiles the corpus was recorded with, in their order: GDI_METADATA_PROFILES="gdi_current healthdcat_r8".
PROFILES = ["gdi_current", "healthdcat_r8"]
_GENERATED = generator.build_schema(PROFILES).schema
SCHEMAS = {
    "dataset": _GENERATED["dataset_fields"],
    # the series schema of the main profile (gdi_current)
    "dataset_series": yaml.safe_load(
        (Path(generator.__file__).parent.parent / "scheming" / "schemas" / "dataset_series_multilingual.yaml").read_text(
            encoding="utf-8"
        )
    )["dataset_fields"],
}

RESOURCE_FIELDS = _GENERATED["resource_fields"]
# CKAN core fields that are not in the schema and are shown as {name, display_name} all the same
CORE_TRANSLATED_FIELDS = ("type",)
# The names the plugin listed when the corpus was recorded: a listed field the dataset had no value for was given
# as None.
RECORDED_PACKAGE_LIST = (
    "access_rights applicable_legislation code_values coding_system creator conforms_to dataset_status dcat_type "
    "has_version health_category health_theme frequency language legal_basis personal_data was_generated_by "
    "publisher publisher_type purpose qualified_attribution qualified_relation quality_annotation spatial_coverage "
    "status theme type"
).split()
RECORDED_RESOURCE_LIST = (
    "access_rights applicable_legislation compress_format conforms_to format hash_algorithm language license "
    "mimetype package_format status"
).split()

CORPUS = json.loads((Path(__file__).parent / "fixtures" / "index_and_api_corpus.json").read_text(encoding="utf-8"))
DATASETS = CORPUS["datasets"]
NAMES = [record["name"] for record in DATASETS]

# {(dataset name, language): {api key: expected value}}: what the API serves now and did not when it was recorded.
DELIBERATE_API_CHANGES: dict = {}


def expected_api(record, language):
    """The recorded dataset as the API serves it now.

    The fields that are shown as ``{name, display_name}`` are the ones the schema marks ``translate`` (they used to
    be a list of names in the plugin). A listed field the dataset had no value for was given as None, and so was a
    listed name that is not a field of the schema at all (``status`` of a dataset, ``access_rights`` of a
    distribution): those are not made up any more.
    """
    expected = deepcopy(record["api_output"][language])
    names = {field["field_name"] for field in SCHEMAS[record["type"]]} | set(CORE_TRANSLATED_FIELDS)
    resource_names = {field["field_name"] for field in RESOURCE_FIELDS}
    for key in RECORDED_PACKAGE_LIST:
        if key in expected and expected[key] is None and key not in names:
            del expected[key]
    for resource in expected.get("resources") or []:
        for key in RECORDED_RESOURCE_LIST:
            if key in resource and resource[key] is None and key not in resource_names:
                del resource[key]
    return {**expected, **DELIBERATE_API_CHANGES.get((record["name"], language), {})}

# List fields that were indexed as the JSON text CKAN gives (``'["a"]'``) and are decoded to a list now: the
# fields that hold a list are read from the schema, not from a list of names kept in the plugin.
NOW_DECODED = ("alternative_title", "analytics", "distribution", "related_resource", "sample", "source")


def _canonical(value):
    """The value with every list of plain values sorted, so that only the content is compared."""
    if isinstance(value, dict):
        return {key: _canonical(item) for key, item in value.items()}
    if isinstance(value, list):
        items = [_canonical(item) for item in value]
        if all(item is None or isinstance(item, (str, int, float, bool)) for item in items):
            items = [item.strip() if isinstance(item, str) else item for item in items]
            return sorted(items, key=repr)
        return items
    return value


def expected_document(record):
    """The recorded document with what indexing does differently now: what changed on purpose."""
    expected = dict(record["index_output"])
    for key in NOW_DECODED:
        if isinstance(expected.get(key), str):
            expected[key] = json.loads(expected[key])
    # the locations of a dataset are a filter now: one Solr value per location (solr: {flatten: [uri]})
    locations = record["index_input"].get("spatial_coverage") or []
    uris = [location["uri"] for location in locations if isinstance(location, dict) and location.get("uri")]
    if uris:
        expected["spatial_coverage_uri"] = uris
    # the labels of the terms were a Solr field of their own (vocab_<field>_search, three fields named in the
    # plugin); they are part of the free text now, with what every field says (test below)
    for key in [key for key in expected if key.startswith("vocab_") and key.endswith("_search")]:
        del expected[key]
    # the JSON text and the objects of the fields of the schema are not indexed: their texts are in the free text
    for name in (field["field_name"] for field in SCHEMAS[record["type"]]):
        for key in [key for key in expected if key == "extras_" + name or key.startswith("extras_%s__" % name)]:
            del expected[key]
        if _is_json_structure(expected.get(name)):
            del expected[name]
    return expected


def _is_json_structure(value):
    if isinstance(value, str) and value.strip()[:1] in ("[", "{"):
        try:
            value = json.loads(value)
        except ValueError:
            return False
    return isinstance(value, dict) or (isinstance(value, list) and any(isinstance(item, dict) for item in value))


def _comparable(record, document):
    """The document as it is compared (see the module docstring)."""
    repeating = {field["field_name"] for field in SCHEMAS[record["type"]] if field.get("repeating_subfields")}
    kept = {
        key: value
        for key, value in document.items()
        if key not in repeating and key != "text" and value not in (None, "", [], {})
    }
    return _canonical(kept)


def _series_lookup(name):
    assert name == "package_show", f"the plugin asked for the action {name}"

    def package_show(context, data_dict):
        try:
            return CORPUS["series"][data_dict["id"]]
        except KeyError:
            raise toolkit.ObjectNotFound()

    return package_show


def _index_translations(terms):
    wanted = set(terms)
    return {term: values for term, values in CORPUS["term_translations_for_index"].items() if term in wanted}


def _index(record):
    fields = SCHEMAS[record["type"]]
    with patch("ckanext.gdi_userportal.plugin.toolkit.get_action", side_effect=_series_lookup), patch(
        "ckanext.gdi_userportal.plugin.get_all_translations", side_effect=_index_translations
    ), patch.object(GdiUserPortalPlugin, "_dataset_fields", return_value=fields):
        return GdiUserPortalPlugin().before_dataset_index(deepcopy(record["index_input"]))


@pytest.mark.parametrize("record", DATASETS, ids=NAMES)
def test_the_indexed_document_is_the_recorded_one(record):
    assert _comparable(record, _index(record)) == _comparable(record, expected_document(record))


@pytest.mark.parametrize("record", DATASETS, ids=NAMES)
def test_the_free_text_has_the_labels_the_search_fields_had(record):
    text = set(_index(record).get("text") or [])
    labels = {
        label
        for key, values in record["index_output"].items()
        if key.startswith("vocab_") and key.endswith("_search")
        for label in values
    }

    assert labels <= text


@pytest.mark.parametrize("record", DATASETS, ids=NAMES)
def test_no_object_and_no_json_text_of_a_schema_field_reaches_solr(record):
    document = _index(record)
    names = {field["field_name"] for field in SCHEMAS[record["type"]]}

    for key, value in document.items():
        assert not key.startswith("extras_") or key[len("extras_") :].split("__")[0] not in names, key
        if key in names:
            assert not _is_json_structure(value), key


@pytest.mark.parametrize("record", DATASETS, ids=NAMES)
def test_the_terms_to_translate_are_the_recorded_ones(record):
    assert sorted(map(str, collect_values_to_translate(deepcopy(record["api_package"])))) == record["terms"]


@pytest.mark.parametrize("language", ["en", "nl"])
@pytest.mark.parametrize("record", DATASETS, ids=NAMES)
def test_the_api_dataset_is_the_recorded_one(record, language):
    shown = replace_package(deepcopy(record["api_package"]), record["term_translations"][language], lang=language)

    assert _canonical(shown) == _canonical(expected_api(record, language))
