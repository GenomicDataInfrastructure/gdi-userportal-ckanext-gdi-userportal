#!/usr/bin/env python

# SPDX-FileCopyrightText: 2024 Stichting Health-RI
#
# SPDX-License-Identifier: Apache-2.0

from dataclasses import dataclass
import logging
from typing import Any, Dict, List, Optional

from ckan.common import config

# -*- coding: utf-8 -*-
from ckan.plugins import toolkit

PACKAGE_REPLACE_FIELDS = [
    "access_rights",
    "applicable_legislation",
    "code_values",
    "coding_system",
    "creator",
    "conforms_to",
    "dcat_type",
    "has_version",
    "health_category",
    "health_theme",
    "frequency",
    "language",
    "legal_basis",
    "personal_data",
    "provenance_activity",
    "publisher",
    "publisher_type",
    "purpose",
    "qualified_attribution",
    "qualified_relation",
    "quality_annotation",
    "spatial_coverage",
    "status",
    "theme",
    "type",
]
RESOURCE_REPLACE_FIELDS = [
    "access_rights",
    "applicable_legislation", 
    "conforms_to",
    "format",
    "hash_algorithm", 
    "language",
    "license",
    "status",
]
ACCESS_SERVICES_REPLACE_FIELDS = [
    "access_rights",
    "applicable_legislation", 
    "conforms_to",
    "creator", 
    "format",
    "hvd_category",
    "language",
    "license", 
    "publisher",
    "theme",
]

NESTED_FIELD_TRANSLATIONS = {
    "qualified_relation": {"role"},
    "qualified_attribution": {"role", "agent"},
    "agent": {"type"},
    "quality_annotation": {"body"},
    "spatial_coverage": {"uri"},
    "creator": {"type"},
    "publisher": {"type"},
    "provenance_activity": {"type", "wasAssociatedWith"},
    "wasAssociatedWith": {"type", "actedOnBehalfOf"},
    "actedOnBehalfOf": {"type"},
}

TRANSLATED_SUFFIX = "_translated"
LANGUAGE_VALUE_FIELDS = {
    "population_coverage",
    "publisher_note",
    "provenance",
    "rights",
    "version_notes"
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
            target_list = _collect_values_for_field(key, value, target_list)
    return target_list


def _collect_values_for_field(field: str, value: Any, target_list: List) -> List:
    if value is None:
        return target_list

    nested_fields = NESTED_FIELD_TRANSLATIONS.get(field)

    if isinstance(value, list):
        for item in value:
            if nested_fields and isinstance(item, dict):
                for nested_field in nested_fields:
                    if nested_field in item:
                        target_list = _collect_values_for_field(
                            nested_field, item[nested_field], target_list
                        )
            else:
                target_list = _append_atomic_value(item, target_list)
        return target_list

    if isinstance(value, dict):
        if nested_fields:
            for nested_field in nested_fields:
                if nested_field in value:
                    target_list = _collect_values_for_field(
                        nested_field, value[nested_field], target_list
                    )
        return target_list

    return _append_atomic_value(value, target_list)


def _append_atomic_value(value: Any, target_list: List) -> List:
    if isinstance(value, list):
        for item in value:
            target_list = _append_atomic_value(item, target_list)
        return target_list

    if isinstance(value, str):
        if value:
            target_list.append(value)
    elif isinstance(value, (int, float)):
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
            access_services = resource.get("access_services", [])
            for access_service in access_services:
                values_to_translate = _select_and_append_values(
                    access_service, ACCESS_SERVICES_REPLACE_FIELDS, values_to_translate
                )
    return list(set(values_to_translate))


def replace_package(data, translation_dict, lang: Optional[str] = None):
    preferred_lang = _get_language(lang)

    _apply_translated_properties(data, preferred_lang)
    _normalize_tags_field(data)

    # Flatten tags to just names (DDS expects string array, not tag objects)
    tags = data.get("tags")
    if isinstance(tags, list):
        data["tags"] = [
            tag.get("name") if isinstance(tag, dict) else tag
            for tag in tags
        ]

    data = _translate_fields(data, PACKAGE_REPLACE_FIELDS, translation_dict)
    resources = data.get("resources", [])

    for resource in resources:
        resource = _translate_fields(resource, RESOURCE_REPLACE_FIELDS, translation_dict)
        access_services = resource.get("access_services", [])
        resource["access_services"] = [
            _translate_fields(access_service, ACCESS_SERVICES_REPLACE_FIELDS, translation_dict)
            for access_service in access_services
        ]
    data["resources"] = resources

    return data


def _normalize_tags_field(data: Any) -> None:
    if not isinstance(data, dict):
        return

    tags = data.get("tags")
    if not isinstance(tags, list):
        return

    normalized_tags = []
    for tag in tags:
        if isinstance(tag, str):
            normalized_tags.append(tag)
            continue
        if isinstance(tag, dict):
            name = tag.get("name") or tag.get("display_name")
            if isinstance(name, str):
                normalized_tags.append(name)
            else:
                log.warning("Dropping tag without string name/display_name: %s", tag)
            continue
        log.warning("Dropping tag with unsupported type: %s", tag)
    data["tags"] = normalized_tags


def _translate_fields(data, fields_list, translation_dict):
    for field in fields_list:
        value = data.get(field)
        if value is None:
            data[field] = None
            continue

        if field in NESTED_FIELD_TRANSLATIONS:
            data[field] = _translate_nested_field(field, value, translation_dict)
            continue

        if isinstance(value, List):
            data[field] = [
                ValueLabel(name=x, display_name=translation_dict.get(x, x)).__dict__
                for x in value
            ]
            continue

        data[field] = ValueLabel(
            name=value, display_name=translation_dict.get(value, value)
        ).__dict__
    return data


def _translate_nested_field(field: str, value: Any, translation_dict: Dict[str, str]) -> Any:
    nested_fields = NESTED_FIELD_TRANSLATIONS.get(field, set())

    if isinstance(value, list):
        return [
            _translate_nested_field(field, item, translation_dict)
            if isinstance(item, (list, dict))
            else _translate_atomic_value(item, translation_dict)
            for item in value
        ]

    if isinstance(value, dict):
        if _is_value_label_dict(value):
            return value
        translated = value.copy()
        for nested_field in nested_fields:
            if nested_field in translated:
                nested_value = translated[nested_field]
                if nested_field in NESTED_FIELD_TRANSLATIONS:
                    translated[nested_field] = _translate_nested_field(
                        nested_field, nested_value, translation_dict
                    )
                else:
                    translated[nested_field] = _translate_atomic_or_collection(
                        nested_value, translation_dict
                    )
        return translated

    return _translate_atomic_value(value, translation_dict)


def _translate_atomic_or_collection(value: Any, translation_dict: Dict[str, str]) -> Any:
    if isinstance(value, list):
        return [
            _translate_atomic_value(item, translation_dict)
            if isinstance(item, (str, int, float))
            else _translate_atomic_or_collection(item, translation_dict)
            for item in value
        ]
    if isinstance(value, dict):
        if _is_value_label_dict(value):
            return value
        return {
            key: _translate_atomic_or_collection(val, translation_dict)
            for key, val in value.items()
        }
    return _translate_atomic_value(value, translation_dict)


def _translate_atomic_value(value: Any, translation_dict: Dict[str, str]) -> Any:
    if isinstance(value, str):
        return ValueLabel(
            name=value, display_name=translation_dict.get(value, value)
        ).__dict__
    return value


def _is_value_label_dict(value: Dict[str, Any]) -> bool:
    if not isinstance(value, dict):
        return False
    if "name" not in value or "display_name" not in value:
        return False
    name_value = value.get("name")
    return isinstance(name_value, str) and name_value is not None


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
    if not isinstance(data, (dict, list)):
        return data

    if isinstance(data, list):
        return [
            _apply_translated_properties(item, preferred_lang, fallback_lang)
            if isinstance(item, (dict, list))
            else item
            for item in data
        ]

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
            existing_value = data.get(base_key)
            # Don't replace list fields (like tags) with translated strings
            if isinstance(existing_value, list):
                continue
            merged_values = value.copy()
            if isinstance(existing_value, dict):
                merged_values.update(existing_value)
            data[base_key] = _select_translated_value(
                merged_values, preferred_lang, fallback_lang
            )
        elif key in LANGUAGE_VALUE_FIELDS and isinstance(value, dict):
            data[key] = _select_translated_value(value, preferred_lang, fallback_lang)

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
    return bool(value) if isinstance(value, (list, dict)) else True
