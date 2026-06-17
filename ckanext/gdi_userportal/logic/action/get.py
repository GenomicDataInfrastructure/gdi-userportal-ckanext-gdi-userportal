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


@toolkit.side_effect_free
def enhanced_package_search(context, data_dict) -> dict:
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
def enhanced_package_show(context, data_dict) -> dict:
    result = toolkit.get_action("package_show")(context, data_dict)
    values_to_translate = collect_values_to_translate(result)
    lang = get_request_language()
    translations = get_translations(values_to_translate, lang=lang)
    return replace_package(result, translations, lang=lang)


@toolkit.side_effect_free
def gdi_filter_help_texts_show(context, data_dict=None) -> dict[str, str]:
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
def gdi_dataset_help_texts_show(context, data_dict=None) -> dict[str, str]:
    data_dict = data_dict or {}
    dataset_type = data_dict.get("type", "dataset")
    requested_keys = _parse_requested_keys(data_dict.get("keys"))
    language = get_preferred_language(get_request_language())

    schema = toolkit.get_action("scheming_dataset_schema_show")(
        context, {"type": dataset_type}
    )

    return _collect_dataset_help_texts(schema, requested_keys, language)


def _collect_help_texts(
    schema: dict[str, object],
    key_property: str,
    text_properties: tuple[str, ...],
    requested_keys: set[str] | None,
    language: str,
) -> dict[str, str]:
    help_texts = {}
    for field in schema.get("dataset_fields", []):
        key = field.get(key_property)
        if not key or (requested_keys is not None and key not in requested_keys):
            continue

        help_text = _first_localized_text(field, text_properties, language)
        if help_text is not None:
            help_texts[key] = help_text

    return help_texts


def _collect_dataset_help_texts(
    schema: dict[str, object],
    requested_keys: set[str] | None,
    language: str,
) -> dict[str, str]:
    help_texts = {}
    help_texts.update(
        _collect_field_help_texts(
            schema.get("dataset_fields", []),
            "",
            requested_keys,
            language,
        )
    )
    help_texts.update(
        _collect_field_help_texts(
            schema.get("resource_fields", []),
            "resource_fields",
            requested_keys,
            language,
        )
    )
    return help_texts


def _collect_field_help_texts(
    fields: object,
    prefix: str,
    requested_keys: set[str] | None,
    language: str,
) -> dict[str, str]:
    if not isinstance(fields, list):
        return {}

    help_texts = {}
    for field in fields:
        if not isinstance(field, dict):
            continue

        field_name = field.get("field_name")
        if not isinstance(field_name, str) or not field_name:
            continue

        key = f"{prefix}.{field_name}" if prefix else field_name
        help_text = _first_localized_text(field, ("help_text",), language)
        if help_text is not None and _should_include_key(key, requested_keys):
            help_texts[key] = help_text

        help_texts.update(
            _collect_field_help_texts(
                field.get("repeating_subfields"),
                key,
                requested_keys,
                language,
            )
        )

    return help_texts


def _should_include_key(key: str, requested_keys: set[str] | None) -> bool:
    return requested_keys is None or key in requested_keys


def _first_localized_text(
    field: dict[str, object], text_properties: tuple[str, ...], language: str
) -> str | None:
    for text_property in text_properties:
        help_text = _localized_text(field.get(text_property), language)
        if help_text:
            return help_text
    return None


def _parse_requested_keys(keys: object) -> set[str] | None:
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


def _localized_text(value: object, language: str) -> str:
    if isinstance(value, dict):
        localized_value = value.get(language)
        if isinstance(localized_value, str):
            return _normalize_help_text(localized_value)

        fallback_value = value.get("en")
        if isinstance(fallback_value, str):
            return _normalize_help_text(fallback_value)

        return ""

    if isinstance(value, str):
        return _normalize_help_text(value)

    return ""


def _normalize_help_text(value: str | None) -> str:
    if value is None:
        return ""

    return " ".join(value.split())
