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
SCHEMAS = {
    "dataset": generator.build_schema(PROFILES).schema["dataset_fields"],
    # the series schema of the main profile (gdi_current)
    "dataset_series": yaml.safe_load(
        (Path(generator.__file__).parent.parent / "scheming" / "schemas" / "dataset_series_multilingual.yaml").read_text(
            encoding="utf-8"
        )
    )["dataset_fields"],
}

CORPUS = json.loads((Path(__file__).parent / "fixtures" / "index_and_api_corpus.json").read_text(encoding="utf-8"))
DATASETS = CORPUS["datasets"]
NAMES = [record["name"] for record in DATASETS]

# {(dataset name, language): {api key: expected value}}: what the API serves now and did not when it was recorded.
DELIBERATE_API_CHANGES: dict = {}

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
    return expected


def _comparable(record, document):
    """The document as it is compared (see the module docstring)."""
    repeating = {field["field_name"] for field in SCHEMAS[record["type"]] if field.get("repeating_subfields")}
    kept = {
        key: value for key, value in document.items() if key not in repeating and value not in (None, "", [], {})
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
def test_the_terms_to_translate_are_the_recorded_ones(record):
    assert sorted(map(str, collect_values_to_translate(deepcopy(record["api_package"])))) == record["terms"]


@pytest.mark.parametrize("language", ["en", "nl"])
@pytest.mark.parametrize("record", DATASETS, ids=NAMES)
def test_the_api_dataset_is_the_recorded_one(record, language):
    shown = replace_package(deepcopy(record["api_package"]), record["term_translations"][language], lang=language)
    expected = {**record["api_output"][language], **DELIBERATE_API_CHANGES.get((record["name"], language), {})}

    assert _canonical(shown) == _canonical(expected)
