# SPDX-FileCopyrightText: 2026 Stichting Health-RI
#
# SPDX-License-Identifier: Apache-2.0

import importlib
from collections import defaultdict

from ckanext.gdi_userportal.migrations.versions.term_translation_helpers import (
    load_csv,
)

MIGRATION = "ckanext.gdi_userportal.migrations.versions.008_vocabulary_translations"


def _labels():
    labels = defaultdict(dict)
    for term, label, lang in load_csv("008_vocabulary_translations.csv"):
        labels[term][lang] = label
    return labels


def test_migration_follows_the_age_range_migration():
    module = importlib.import_module(MIGRATION)

    assert module.revision == "008_vocabulary_translations"
    assert module.down_revision == "007_status_translations"


def test_inspire_responsible_party_roles_have_english_and_dutch_labels():
    labels = _labels()

    for scheme in ("http", "https"):
        point_of_contact = labels[
            f"{scheme}://inspire.ec.europa.eu/metadata-codelist/ResponsiblePartyRole/pointOfContact"
        ]
        assert point_of_contact == {"en": "Point of Contact", "nl": "Contact"}


def test_iana_link_relations_are_labelled_for_both_schemes():
    labels = _labels()

    for scheme in ("http", "https"):
        assert labels[f"{scheme}://www.iana.org/assignments/relation/related"] == {
            "en": "Related"
        }
        assert labels[f"{scheme}://www.iana.org/assignments/relation/first"] == {
            "en": "First"
        }


def test_spdx_checksum_algorithms_use_the_spdx_individual_names():
    labels = _labels()
    spdx = "http://spdx.org/rdf/terms#checksumAlgorithm_"

    assert labels[spdx + "md5"] == {"en": "MD5"}
    assert labels[spdx + "sha256"] == {"en": "SHA-256"}
    assert labels[spdx + "blake2b256"] == {"en": "BLAKE2b-256"}
    # spellings that are not individuals of the SPDX ontology
    assert spdx + "SHA256" not in labels
    assert spdx + "blake2b_256" not in labels


def test_every_row_is_a_complete_unique_term_and_language_pair():
    rows = load_csv("008_vocabulary_translations.csv")
    pairs = [(term, lang) for term, _, lang in rows]

    assert len(pairs) == len(set(pairs))
    assert {lang for _, _, lang in rows} == {"en", "nl"}
