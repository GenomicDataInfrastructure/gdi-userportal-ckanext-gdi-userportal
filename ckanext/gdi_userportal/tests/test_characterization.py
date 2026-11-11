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

A change that moves any of this has to say so: list it in ``DELIBERATE_INDEX_CHANGES`` or
``DELIBERATE_API_CHANGES`` with the reason, as ``test_gdi_current_golden.py`` does for the schema.

The order of a list of plain values is not compared: Solr does not care, and the plugin builds some of them from sets.
"""

import json
from copy import deepcopy
from pathlib import Path
from unittest.mock import patch

import pytest
from ckan.plugins import toolkit

from ckanext.gdi_userportal.logic.action.translation_utils import (
    collect_values_to_translate,
    replace_package,
)
from ckanext.gdi_userportal.plugin import GdiUserPortalPlugin

CORPUS = json.loads((Path(__file__).parent / "fixtures" / "index_and_api_corpus.json").read_text(encoding="utf-8"))
DATASETS = CORPUS["datasets"]
NAMES = [record["name"] for record in DATASETS]

# {dataset name: {solr field: expected value}}: what indexing does now and did not when the corpus was recorded.
DELIBERATE_INDEX_CHANGES: dict = {}
# {(dataset name, language): {api key: expected value}}: the same for what the API serves.
DELIBERATE_API_CHANGES: dict = {}


def _canonical(value):
    """The value with every list of plain values sorted, so that only the content is compared."""
    if isinstance(value, dict):
        return {key: _canonical(item) for key, item in value.items()}
    if isinstance(value, list):
        items = [_canonical(item) for item in value]
        if all(item is None or isinstance(item, (str, int, float, bool)) for item in items):
            return sorted(items, key=repr)
        return items
    return value


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
    with patch("ckanext.gdi_userportal.plugin.toolkit.get_action", side_effect=_series_lookup), patch(
        "ckanext.gdi_userportal.plugin.get_all_translations", side_effect=_index_translations
    ):
        return GdiUserPortalPlugin().before_dataset_index(deepcopy(record["index_input"]))


@pytest.mark.parametrize("record", DATASETS, ids=NAMES)
def test_the_indexed_document_is_the_recorded_one(record):
    expected = {**record["index_output"], **DELIBERATE_INDEX_CHANGES.get(record["name"], {})}

    assert _canonical(_index(record)) == _canonical(expected)


@pytest.mark.parametrize("record", DATASETS, ids=NAMES)
def test_the_terms_to_translate_are_the_recorded_ones(record):
    assert sorted(map(str, collect_values_to_translate(deepcopy(record["api_package"])))) == record["terms"]


@pytest.mark.parametrize("language", ["en", "nl"])
@pytest.mark.parametrize("record", DATASETS, ids=NAMES)
def test_the_api_dataset_is_the_recorded_one(record, language):
    shown = replace_package(deepcopy(record["api_package"]), record["term_translations"][language], lang=language)
    expected = {**record["api_output"][language], **DELIBERATE_API_CHANGES.get((record["name"], language), {})}

    assert _canonical(shown) == _canonical(expected)
