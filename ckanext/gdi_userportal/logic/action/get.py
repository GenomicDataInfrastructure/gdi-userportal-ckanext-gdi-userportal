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
    translations = get_translations(values_to_translate)
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
    translations = get_translations(values_to_translate)
    return replace_package(result, translations)


@toolkit.side_effect_free
def enhanced_organization_list(context, data_dict) -> Dict:
    names = toolkit.get_action("organization_list")(context, data_dict)

    results = []
    for name in names:
        organization_show_response = toolkit.get_action("organization_show")(
            context, {"id": name}
        )
        results.append(organization_show_response.result)

    return {"count": len(results), "results": results}
