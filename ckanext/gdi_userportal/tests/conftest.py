# SPDX-FileCopyrightText: 2026 Stichting Health-RI
#
# SPDX-License-Identifier: Apache-2.0

"""
The dataset schema that the indexing reads.

``before_dataset_index`` asks scheming for the schema of the dataset type and flattens what the ``solr`` key
of its fields says. The tests that call it use the schema the generator makes from the packs, as the stack
does, instead of a running scheming plugin.
"""

from unittest.mock import patch

import pytest

# Imported inside the fixtures: the tests of tests/profile_packs run without CKAN (see its conftest).


def _patched_schema(profiles):
    from ckanext.gdi_userportal.plugin import GdiUserPortalPlugin
    from ckanext.gdi_userportal.profile_packs import generator

    fields = generator.build_schema(profiles).schema["dataset_fields"]
    return fields, patch.object(GdiUserPortalPlugin, "_dataset_fields", return_value=fields)


@pytest.fixture
def indexing_schema():
    """gdi_current first (the deployment default): its agents have an identifier and a country."""
    fields, patched = _patched_schema(["gdi_current", "healthdcat_r8"])
    with patched:
        yield fields


@pytest.fixture
def r8_indexing_schema():
    """healthdcat_r8 first: the landing page and the type of a dataset are lists."""
    fields, patched = _patched_schema(["healthdcat_r8", "gdi_current"])
    with patched:
        yield fields
