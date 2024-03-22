#!/usr/bin/env python

# SPDX-FileCopyrightText: 2024 Stichting Health-RI
#
# SPDX-License-Identifier: Apache-2.0

# -*- coding: utf-8 -*-
from ckan.plugins import toolkit
from typing import Any, List, Dict
from ckan.common import request, config


def get_translations(values_to_translate: List) -> Dict[str, str]:
    """Calls term_translation_show action with a list of values to translate"""
    language = _get_language()
    translations = toolkit.get_action('term_translation_show')(
        {},
        {'terms': values_to_translate,
         'lang_codes': language})

    translations = {transl_item["term"]: transl_item["term_translation"] for transl_item in translations}
    return translations


def _get_language() -> str:
    """
    Tries to get default language from environment variables/ckan config, defaults to English
    """
    language = "en"
    try:
        language = request.environ['CKAN_LANG']
    except (TypeError, KeyError):
        try:
            language = config['ckan.locale_default']
        except KeyError:
            pass
    return language


def nested_replace(data: Any, replace_dict: Dict) -> Any:
    """
    Walks over a json tree, replaces string values starting with 'http' with value-label objects
    where 'value' is an original field value and `label` a replacement found in replacement_dict or None
    """
    if isinstance(data, list):
        return [nested_replace(item, replace_dict) for item in data]

    if isinstance(data, dict):
        return {key: nested_replace(value, replace_dict)
                for key, value in data.items()}

    if isinstance(data, str) and data.startswith("http"):
        return {"value": data, "label": replace_dict.get(data, None)}
    else:
        return data


def collect_values_to_translate(data: Any, values_to_translate: List) -> List:
    """Walks over a json tree and returns a list of string values starting with 'http'"""
    if isinstance(data, str) and data.startswith("http"):
        values_to_translate.append(data)
    elif isinstance(data, list):
        for item in data:
            collect_values_to_translate(item, values_to_translate)
    elif isinstance(data, dict):
        for key, value in data.items():
            collect_values_to_translate(value, values_to_translate)
    return values_to_translate
