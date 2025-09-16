#!/usr/bin/env python

# SPDX-FileCopyrightText: 2024 Stichting Health-RI
# SPDX-FileContributor: PNED G.I.E.
#
# SPDX-License-Identifier: Apache-2.0

# -*- coding: utf-8 -*-

import logging

from ckan.plugins import toolkit
from ckanext.gdi_userportal.logic.action.translation_utils import (
    collect_values_to_translate,
    get_translations,
    replace_package,
    replace_search_facets,
)
from typing import Dict

log = logging.getLogger(__name__)


@toolkit.side_effect_free
def enhanced_package_search(context, data_dict) -> Dict:
    result = toolkit.get_action("package_search")(context, data_dict)
    values_to_translate = collect_values_to_translate(result)
    lang = toolkit.request.headers.get("Accept-Language")
    translations = get_translations(values_to_translate, lang=lang)
    result["results"] = [
        replace_package(package, translations) for package in result["results"]
    ]
    if "search_facets" in result.keys():
        result["search_facets"] = replace_search_facets(
            result["search_facets"], translations
        )
    return result


@toolkit.side_effect_free
def enhanced_package_show(context, data_dict) -> Dict:
    result = toolkit.get_action("package_show")(context, data_dict)
    values_to_translate = collect_values_to_translate(result)
    lang = toolkit.request.headers.get("Accept-Language")
    translations = get_translations(values_to_translate)
    return replace_package(result, translations)
