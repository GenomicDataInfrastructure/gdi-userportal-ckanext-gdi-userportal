#!/usr/bin/env python

# SPDX-FileCopyrightText: 2024 Stichting Health-RI
#
# SPDX-License-Identifier: Apache-2.0

from dataclasses import dataclass
import logging
from typing import Any, Dict, List, Optional

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
    "dcat_type",
]
RESOURCE_REPLACE_FIELDS = ["format", "language"]
TRANSLATED_SUFFIX = "_translated"
LANGUAGE_VALUE_FIELDS = {
    "population_coverage",
    "publisher_note",
    "provenance",
    "rights",
}
DEFAULT_FALLBACK_LANG = "en"
SUPPORTED_LANGUAGES = {DEFAULT_FALLBACK_LANG, "nl"}

log = logging.getLogger(__name__)

@dataclass
class ValueLabel:
    name: str
    display_name: str
    count: int = None


def get_translations(values_to_translate: List, lang: str = DEFAULT_FALLBACK_LANG) -> Dict[str, str]:
    """Calls term_translation_show action with a list of values to translate"""
    pref_language = _get_language(lang)

    translation_table = toolkit.get_action("term_translation_show")(
        {},
        {
            "terms": values_to_translate,
            "lang_codes": (pref_language, DEFAULT_FALLBACK_LANG),
        },
    )

    # First fill the dictionary with the fallback language
    translations = {
        transl_item["term"]: transl_item["term_translation"]
        for transl_item in translation_table
        if (transl_item["lang_code"] == DEFAULT_FALLBACK_LANG)
    }

    # Override with preferred language
    for transl_item in translation_table:
        if transl_item["lang_code"] == pref_language:
            translations[transl_item["term"]] = transl_item["term_translation"]

    return translations


def _normalize_language(lang_value: Any) -> str:
    if not isinstance(lang_value, str) or not lang_value.strip():
        return ""

    primary = lang_value.split(",", 1)[0]
    primary = primary.split(";", 1)[0].strip()
    if not primary:
        return ""

    primary = primary.replace("_", "-").split("-", 1)[0]
    return primary.lower()


def _get_language(lang: str) -> str:
    """
    Tries to get default language from environment variables/ckan config, defaults to English
    """
    language = _normalize_language(lang)

    if not language:
        log.warning(
            "Could not determine preferred language from request headers, falling back to CKAN config"
        )
        language = _normalize_language(config.get("ckan.locale_default"))

    if language not in SUPPORTED_LANGUAGES:
        language = DEFAULT_FALLBACK_LANG

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


def replace_package(data, translation_dict, lang: Optional[str] = None):
    preferred_lang = _get_language(lang)

    _apply_translated_properties(data, preferred_lang)

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


def replace_search_facets(data, translation_dict, lang):
    preferred_lang = _get_language(lang)
    new_facets = {}
    for key, facet in data.items():
        title = facet["title"]
        new_facets[key] = {
            "title": get_translations([title], lang=preferred_lang).get(title, title)
        }
        new_facets[key]["items"] = [
            _change_facet(item, translation_dict) for item in facet["items"]
        ]
    return new_facets


def _apply_translated_properties(data: Any, preferred_lang: str, fallback_lang: str = DEFAULT_FALLBACK_LANG):
    if isinstance(data, dict):
        for key, value in list(data.items()):
            if isinstance(value, dict):
                _apply_translated_properties(value, preferred_lang, fallback_lang)
            elif isinstance(value, list):
                data[key] = [
                    _apply_translated_properties(item, preferred_lang, fallback_lang)
                    if isinstance(item, (dict, list))
                    else item
                    for item in value
                ]

        for key, value in list(data.items()):
            if key.endswith(TRANSLATED_SUFFIX) and isinstance(value, dict):
                base_key = key[:-len(TRANSLATED_SUFFIX)]
                data[base_key] = _select_translated_value(value, preferred_lang, fallback_lang)
            elif key in LANGUAGE_VALUE_FIELDS and isinstance(value, dict):
                data[key] = _select_translated_value(value, preferred_lang, fallback_lang)
        return data

    if isinstance(data, list):
        return [
            _apply_translated_properties(item, preferred_lang, fallback_lang)
            if isinstance(item, (dict, list))
            else item
            for item in data
        ]

    return data


def _select_translated_value(values: Dict[str, Any], preferred_lang: str, fallback_lang: str) -> Any:
    if not isinstance(values, dict):
        return values

    for lang in (preferred_lang, fallback_lang):
        translated = values.get(lang)
        if _has_content(translated):
            return translated

    for translated in values.values():
        if _has_content(translated):
            return translated

    return next(iter(values.values()), "")


def _has_content(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, (list, dict)):
        return bool(value)
    return True
