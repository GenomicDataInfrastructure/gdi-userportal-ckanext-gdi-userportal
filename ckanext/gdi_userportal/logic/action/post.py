# SPDX-FileCopyrightText: 2024 Stichting Health-RI
# SPDX-FileContributor: PNED G.I.E.
#
# SPDX-License-Identifier: Apache-2.0

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
def enhanced_package_search(context, data_dict=None) -> Dict:
    data_dict = data_dict or toolkit.request.json
    if not data_dict:
        raise toolkit.ValidationError("data_dict and request body cannot be both empty")

    try:
        result = toolkit.get_action("package_search")(context, data_dict)
        values_to_translate = collect_values_to_translate(result)
        lang = toolkit.request.headers.get("Accept-Language")
        translations = get_translations(values_to_translate, lang=lang)

        result["results"] = [
            replace_package(package, translations, lang=lang)
            for package in result["results"]
        ]

        if "search_facets" in result:
            result["search_facets"] = replace_search_facets(
                result["search_facets"], translations, lang=lang
            )

        return result
    except Exception as e:
        _handle_exception(e, "Error in enhanced_package_search")


def _handle_exception(e: Exception, message: str):
    log.error(f"{message}: %s", str(e))
    if isinstance(e, toolkit.ObjectNotFound):
        raise toolkit.ObjectNotFound("No results found for the provided query.")
    raise toolkit.ValidationError(f"An error occurred: {str(e)}")
