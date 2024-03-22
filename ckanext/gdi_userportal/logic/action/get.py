#!/usr/bin/env python

# SPDX-FileCopyrightText: 2024 Stichting Health-RI
#
# SPDX-License-Identifier: Apache-2.0

# -*- coding: utf-8 -*-

import logging

from ckan.plugins import toolkit
from ckanext.gdi_userportal.logic.action.fetcher import (
    DatasetFetcher,
    PublisherFetcher,
    ThemeFetcher,
)
from ckanext.gdi_userportal.logic.action.translation_utils import (nested_replace, collect_values_to_translate,
                                                                   get_translations)
from typing import List, Dict, Union

log = logging.getLogger(__name__)


@toolkit.side_effect_free
def scheming_package_show(context, data_dict):
    """
    Function made to be called on Dataplatform Portal. It provides an alternative for package_show,
    returning information in a format that is fitted to what the Dataplatform Portal needs

    :param context
    :param data_dict

    :param include_labels: If set to True will replace the value of the field,
    with a dictionary with 2 keys 'value' and 'labels' a dictionary which
    contains all the labels for that value in all languages.(default: `False`)
    :type include_labels: bool
    """

    pkg_dict = toolkit.get_action("package_show")(context, data_dict)
    schema = toolkit.get_action("scheming_dataset_schema_show")(context, data_dict)
    dataset_fields = schema["dataset_fields"]

    new_pkg_dict = {}
    fields_not_in_schema_that_should_be_visible = [
        {
            "name": "metadata_created",
            "label": {
                "en": "Metadata Created",
                "nl": "Gecreëerd",
                "sv": "Metadata skapad",
            },
        },
        {
            "name": "metadata_modified",
            "label": {
                "en": "Metadata Modified",
                "nl": "Laatst gewijzigd",
                "sv": "Metadata modifierad",
            },
        },
        {
            "name": "organization",
            "label": {"en": "Organization", "nl": "Organisatie", "sv": "Organization"},
        },
        {
            "name": "license_title",
            "label": {"en": "License", "nl": "Licentie", "sv": "Licens"},
        },
    ]
    fields_in_schema_that_should_not_be_visible = ["owner_org"]

    for field in dataset_fields:
        field_name = field["field_name"]
        try:
            value = pkg_dict[field_name]
        except KeyError:
            continue

        # Add Visibility to be showed in the Portal
        # Default visibility is True
        # If display_snippet = hidden.html or null OR part of the exceptions list then visible false

        if (
            "display_snippet" in field
            and field["display_snippet"] in [None, "hidden.html"]
        ) or field_name in fields_in_schema_that_should_not_be_visible:
            visible = False
        else:
            visible = True

        field_label = field.get("label", None)
        choices = toolkit.h.scheming_field_choices(field)

        if choices is None:
            new_pkg_dict[field_name] = {
                "value": value,
                "value_label": None,
                "field_label": field_label,
                "visible": visible,
            }
            del pkg_dict[field_name]
            continue

        for choice in choices:
            if choice["value"] == value:
                new_pkg_dict[field_name] = {
                    "value": value,
                    "value_label": choice["label"],
                    "field_label": field_label,
                    "visible": visible,
                }
                del pkg_dict[field_name]
                break

    for fieldname in pkg_dict:
        field_label = None
        visible = any(
            fieldname in field_dict["name"]
            for field_dict in fields_not_in_schema_that_should_be_visible
        )
        if visible:
            for field_dict in fields_not_in_schema_that_should_be_visible:
                if field_dict["name"] == fieldname:
                    field_label = field_dict["label"]

        default_field_dict = {
            "value": pkg_dict[fieldname],
            "value_label": None,
            "field_label": field_label,
            "visible": visible,
        }
        new_pkg_dict[fieldname] = default_field_dict

    return new_pkg_dict


@toolkit.side_effect_free
def get_keyword_list(context, data_dict) -> Dict[str, Union[int, list[str]]]:
    keywords = list(set(toolkit.get_action("tag_list")(context, data_dict)))
    return {"count": len(keywords), "results": keywords}


@toolkit.side_effect_free
def get_catalogue_list(context, data_dict) -> Dict[str, Union[int, list[str]]]:
    organizations = list(
        set(
            toolkit.get_action("organization_list")(
                context, {"permission_list": "read"}
            )
        )
    )
    return {"count": len(organizations), "results": organizations}


@toolkit.side_effect_free
def get_publisher_list(context, data_dict) -> Dict[str, Union[int, List[str]]]:
    return PublisherFetcher(context, batch_size=256).get_prop_list()


@toolkit.side_effect_free
def get_theme_list(context, data_dict) -> Dict[str, Union[int, List[str]]]:
    return ThemeFetcher(context, batch_size=256).get_prop_list()


@toolkit.side_effect_free
def get_dataset_list(context, data_dict) -> Dict[str, Union[int, List[str]]]:
    return DatasetFetcher(context, batch_size=256).get_prop_list()


@toolkit.side_effect_free
def get_with_url_labels(context, data_dict) -> Dict:
    """
    A wrapper for an action function: calls the function and replaces all starting with http string values with
    value-label object
    "action_name" should be a valid name of an action function returning a dictionary
    """
    try:
        action_name = data_dict["action_name"]
    except KeyError:
        raise KeyError(f"'action_name' parameter should be provided")
    del data_dict["action_name"]
    result = toolkit.get_action(action_name)(context, data_dict)
    values_to_translate = []
    for key, value in result.items():
        collect_values_to_translate(value, values_to_translate)
    values_to_translate = list(set(values_to_translate))
    translations = get_translations(values_to_translate)
    result = nested_replace(result, translations)
    return result
