#!/usr/bin/env python

# SPDX-FileCopyrightText: 2024 Stichting Health-RI
#
# SPDX-License-Identifier: Apache-2.0

from dataclasses import dataclass
from typing import Any, Dict, List

from ckan.common import config, request

# -*- coding: utf-8 -*-
from ckan.plugins import toolkit

PACKAGE_REPLACE_FIELDS = [
    "access_rights",
    "conforms_to",
    "has_version",
    "language",
    "spatial_uri",
    "theme",
]
RESOURCE_REPLACE_FIELDS = ["format"]
DEFAULT_FALLBACK_LANG = "en"


@dataclass
class ValueLabel:
    name: str
    display_name: str
    count: int = None


def get_translations(values_to_translate: List) -> Dict[str, str]:
    """Calls term_translation_show action with a list of values to translate"""
    pref_language = _get_language()
    fallback_language = config.get("ckan.locale_default", DEFAULT_FALLBACK_LANG)

    translation_table = toolkit.get_action("term_translation_show")(
        {},
        {
            "terms": values_to_translate,
            "lang_codes": (pref_language, fallback_language),
        },
    )

    # First fill the dictionary with the fallback language
    translations = {
        transl_item["term"]: transl_item["term_translation"]
        for transl_item in translation_table
        if (transl_item["lang_code"] == fallback_language)
    }

    # Override with preferred language
    for transl_item in translation_table:
        if transl_item["lang_code"] == pref_language:
            translations[transl_item["term"]] = transl_item["term_translation"]

    return translations


def _get_language() -> str:
    """
    Tries to get default language from environment variables/ckan config, defaults to English
    """
    language = DEFAULT_FALLBACK_LANG
    try:
        language = request.environ["CKAN_LANG"]
    except (TypeError, KeyError):
        try:
            language = config["ckan.locale_default"]
        except KeyError:
            pass
    return language


def _select_and_append_values(
    data_item: Dict, fields_list: List, target_list: List
) -> List:
    for key, value in data_item.items():
        if key in fields_list:
            if isinstance(value, list):
                target_list.extend(value)
            else:
                target_list.append(value)
    return target_list


def collect_values_to_translate(data: Any) -> List:
    values_to_translate = []
    if not isinstance(data, List):
        data = [data]
    for package in data:
        values_to_translate = _select_and_append_values(
            package, PACKAGE_REPLACE_FIELDS, values_to_translate
        )
        resources = package.get("resources", [])
        for resource in resources:
            values_to_translate = _select_and_append_values(
                resource, RESOURCE_REPLACE_FIELDS, values_to_translate
            )
    return list(set(values_to_translate))


def replace_package(data, translation_dict):
    data = _translate_fields(data, PACKAGE_REPLACE_FIELDS, translation_dict)
    resources = data.get("resources", [])
    data["resources"] = [
        _translate_fields(item, RESOURCE_REPLACE_FIELDS, translation_dict)
        for item in resources
    ]
    return data


def _translate_fields(data, fields_list, translation_dict):
    for field in fields_list:
        value = data.get(field)
        new_value = None
        if value:
            if isinstance(value, List):
                new_value = [
                    ValueLabel(name=x, display_name=translation_dict.get(x, x)).__dict__
                    for x in value
                ]
            else:
                new_value = ValueLabel(
                    name=value, display_name=translation_dict.get(value, value)
                ).__dict__
        data[field] = new_value
    return data


def _change_facet(facet, translation_dict):
    name = facet["name"]
    facet["display_name"] = translation_dict.get(name, name)
    return facet


def replace_search_facets(data, translation_dict):
    new_facets = {}
    for key, facet in data.items():
        title = facet["title"]
        new_facets[key] = {"title": get_translations([title]).get(title, title)}
        new_facets[key]["items"] = [
            _change_facet(item, translation_dict) for item in facet["items"]
        ]
    return new_facets
