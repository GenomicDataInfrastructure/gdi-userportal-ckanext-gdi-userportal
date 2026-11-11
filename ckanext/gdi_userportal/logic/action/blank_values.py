# SPDX-FileCopyrightText: 2026 Stichting Health-RI
#
# SPDX-License-Identifier: Apache-2.0

"""
Datasets are saved without the fields that hold nothing.

``package_create`` and ``package_update`` are the one place every save goes through: the edit form, the API,
``package_patch`` (it hands the merged dataset to ``package_update``, so a field that is cleared is dropped
and gone) and the harvesters. A schema field that is empty is left out of the dataset before it is validated,
so it is never stored as an extra (``blank_values.py`` says what is empty). A required field that is
empty is still reported by the validation, as missing.
"""

import logging

from ckan import model
from ckan.plugins import toolkit

from ckanext.gdi_userportal import blank_values, schema_access

log = logging.getLogger(__name__)

# what is part of a dataset but not saved as an extra, besides its own columns
_NOT_EXTRAS = {"tags", "groups", "extras", "resources", "organization", "relationships_as_subject", "relationships_as_object"}


def core_dataset_fields():
    return set(model.package_table.c.keys()) | _NOT_EXTRAS


def core_resource_fields():
    return set(model.resource_table.c.keys())


def _dataset_type(data_dict):
    """The type of the dataset; an update that does not name it keeps the type the dataset has."""
    dataset_type = data_dict.get("type")
    if dataset_type:
        return dataset_type
    package = model.Package.get(data_dict.get("id") or data_dict.get("name") or "")
    return package.type if package else None


def without_blank_values(data_dict):
    """The dataset without its empty schema fields; as it came when that cannot be done (a save is never stopped)."""
    try:
        dataset_type = _dataset_type(data_dict)
        schema = schema_access.dataset_schema(dataset_type)
        return blank_values.prune_dataset(
            data_dict,
            schema.get("dataset_fields"),
            schema.get("resource_fields"),
            core_dataset_fields(),
            core_resource_fields(),
        )
    except Exception:  # noqa: BLE001 - a dataset with empty values is better than one that cannot be saved
        log.warning("Could not leave the empty values out of a dataset", exc_info=True)
        return data_dict


@toolkit.chained_action
def package_create(original_action, context, data_dict):
    return original_action(context, without_blank_values(data_dict))


@toolkit.chained_action
def package_update(original_action, context, data_dict):
    return original_action(context, without_blank_values(data_dict))
