#!/usr/bin/env python

# SPDX-FileCopyrightText: 2024 Stichting Health-RI
# SPDX-FileContributor: PNED G.I.E.
#
# SPDX-License-Identifier: Apache-2.0

# -*- coding: utf-8 -*-

import json
from ckan.plugins import toolkit
from ckanext.gdi_userportal.logic.action.translation_utils import (
    collect_values_to_translate,
    get_request_language,
    get_preferred_language,
    get_translations,
    replace_package,
    replace_search_facets,
)
from typing import Any, Dict, Optional, Set, Tuple


@toolkit.side_effect_free
def enhanced_package_search(context, data_dict) -> Dict:
    result = toolkit.get_action("package_search")(context, data_dict)
    values_to_translate = collect_values_to_translate(result)
    lang = get_request_language()
    translations = get_translations(values_to_translate, lang=lang)
    result["results"] = [
        replace_package(package, translations, lang=lang)
        for package in result["results"]
    ]
    if "search_facets" in result.keys():
        result["search_facets"] = replace_search_facets(
            result["search_facets"], translations, lang=lang
        )
    return result


@toolkit.side_effect_free
def enhanced_package_show(context, data_dict) -> Dict:
    result = toolkit.get_action("package_show")(context, data_dict)
    values_to_translate = collect_values_to_translate(result)
    lang = get_request_language()
    translations = get_translations(values_to_translate, lang=lang)
    return replace_package(result, translations, lang=lang)


@toolkit.side_effect_free
def gdi_filter_help_texts_show(context, data_dict=None) -> Dict[str, str]:
    data_dict = data_dict or {}
    dataset_type = data_dict.get("type", "dataset")
    requested_keys = _parse_requested_keys(data_dict.get("keys"))
    language = get_preferred_language(get_request_language())

    schema = toolkit.get_action("scheming_dataset_schema_show")(
        context, {"type": dataset_type}
    )

    return _collect_help_texts(
        schema,
        "facet_key",
        ("filter_help_text", "help_text"),
        requested_keys,
        language,
    )


@toolkit.side_effect_free
def gdi_dataset_help_texts_show(context, data_dict=None) -> Dict[str, str]:
    data_dict = data_dict or {}
    dataset_type = data_dict.get("type", "dataset")
    requested_keys = _parse_requested_keys(data_dict.get("keys"))
    language = get_preferred_language(get_request_language())

    schema = toolkit.get_action("scheming_dataset_schema_show")(
        context, {"type": dataset_type}
    )

    return _collect_help_texts(
        schema,
        "field_name",
        ("help_text",),
        requested_keys,
        language,
    )


def _collect_help_texts(
    schema: Dict[str, Any],
    key_property: str,
    text_properties: Tuple[str, ...],
    requested_keys: Optional[Set[str]],
    language: str,
) -> Dict[str, str]:
    help_texts = {}
    for field in schema.get("dataset_fields", []):
        key = field.get(key_property)
        if not key or (requested_keys is not None and key not in requested_keys):
            continue

        help_text = _first_localized_text(field, text_properties, language)
        if help_text is not None:
            help_texts[key] = help_text

    return help_texts


def _first_localized_text(
    field: Dict[str, Any], text_properties: Tuple[str, ...], language: str
) -> Optional[str]:
    for text_property in text_properties:
        help_text = _localized_text(field.get(text_property), language)
        if help_text:
            return help_text
    return None


def _parse_requested_keys(keys: Any) -> Optional[Set[str]]:
    if keys is None or keys == "":
        return None

    if isinstance(keys, str):
        try:
            keys = json.loads(keys)
        except ValueError:
            keys = [key.strip() for key in keys.split(",")]

    if not isinstance(keys, (list, tuple, set)):
        raise toolkit.ValidationError({"keys": ["Must be a list of strings"]})

    parsed_keys = {key.strip() for key in keys if isinstance(key, str) and key.strip()}
    return parsed_keys


def _localized_text(value: Any, language: str) -> str:
    if isinstance(value, dict):
        return value.get(language) or value.get("en") or ""

    if isinstance(value, str):
        return value

    return ""
