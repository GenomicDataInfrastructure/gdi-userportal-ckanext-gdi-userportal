# SPDX-FileCopyrightText: 2026 Stichting Health-RI
#
# SPDX-License-Identifier: Apache-2.0

"""
The dataset schema as the running CKAN has loaded it.

The indexing (``plugin.py``) and the translation of the API (``logic/action/translation_utils.py``) both follow
what the fields of that schema say about themselves (``profile_packs/README.md``, the keys ``solr``,
``translate`` and ``agent``), so they read the schema here and nowhere else.
"""

import logging
from typing import List, Optional

from ckan.plugins import toolkit

log = logging.getLogger(__name__)

DEFAULT_DATASET_TYPE = "dataset"


def dataset_schema(dataset_type: Optional[str] = None) -> dict:
    """The scheming schema of a dataset type; an empty one when the type has none or scheming cannot be asked."""
    try:
        schema = toolkit.h.scheming_get_dataset_schema(dataset_type or DEFAULT_DATASET_TYPE)
    except Exception:  # noqa: BLE001 - a dataset is still shown and indexed without its schema
        log.warning("Could not read the dataset schema of %r", dataset_type, exc_info=True)
        return {}
    return schema or {}


def dataset_fields(dataset_type: Optional[str] = None) -> List[dict]:
    return dataset_schema(dataset_type).get("dataset_fields") or []


def resource_fields(dataset_type: Optional[str] = None) -> List[dict]:
    return dataset_schema(dataset_type).get("resource_fields") or []
