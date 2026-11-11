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

from ckanext.gdi_userportal import schema_access
from ckanext.gdi_userportal.profile_packs import schema_fields

# Which fields of a dataset are shown as {name, display_name}, which hold agents, and which hold a text per
# language is not decided here but by the ``translate``, ``agent`` and fluent fields of the dataset schema
# (profile_packs/README.md). Only the CKAN core fields that are not in the schema are named here.
CORE_TRANSLATED_FIELDS = ("type",)

TRANSLATED_SUFFIX = "_translated"

DEFAULT_FALLBACK_LANG = "en"
DEFAULT_LANGUAGES = (DEFAULT_FALLBACK_LANG, "nl")

log = logging.getLogger(__name__)

@dataclass
class ValueLabel:
    name: str
    display_name: str
    count: int = None


def get_translations(values_to_translate: List, lang: Optional[str] = DEFAULT_FALLBACK_LANG) -> Dict[str, str]:
    """Calls term_translation_show action with a list of values to translate"""
    pref_language = get_preferred_language(lang)

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


def get_request_language() -> Optional[str]:
    try:
        return toolkit.request.headers.get("Accept-Language")
    except RuntimeError:
        return None


def _deduplicate_non_empty_strings(values: List[Any]) -> List[str]:
    seen = set()
    deduplicated = []

    for value in values:
        if not isinstance(value, str):
            continue

        normalized = value.strip()
        if not normalized or normalized in seen:
            continue

        seen.add(normalized)
        deduplicated.append(normalized)

    return deduplicated


def get_all_translations(values_to_translate: List[Any]) -> Dict[str, List[str]]:
    """Return all known translations for each term, grouped by term."""
    terms = _deduplicate_non_empty_strings(values_to_translate)
    if not terms:
        return {}

    translation_table = toolkit.get_action("term_translation_show")(
        {},
        {"terms": terms},
    )

    translations = {term: [] for term in terms}

    for translation_row in translation_table:
        term = translation_row.get("term")
        translated_value = translation_row.get("term_translation")
        if not isinstance(term, str) or not isinstance(translated_value, str):
            continue
        if term not in translations:
            translations[term] = []
        translations[term].append(translated_value)

    return {
        term: _deduplicate_non_empty_strings(values)
        for term, values in translations.items()
        if values
    }


def _normalize_language(lang_value: Any) -> str:
    if not isinstance(lang_value, str) or not lang_value.strip():
        return ""

    primary = lang_value.split(",", 1)[0]
    primary = primary.split(";", 1)[0].strip()
    if not primary:
        return ""

    primary = primary.replace("_", "-").split("-", 1)[0]
    return primary.lower()


def supported_languages() -> List[str]:
    """The languages the API answers in: English and Dutch, and every other ``form_languages`` of the dataset schema.

    ``form_languages`` (GDI_METADATA_FORM_LANGUAGES) says what the metadata form offers, which a deployment may
    limit to English while its portal still shows the labels in Dutch, so it adds languages and never removes one.
    """
    languages = schema_access.dataset_schema().get("form_languages")
    extra = [_normalize_language(code) for code in languages] if isinstance(languages, list) else []
    return list(dict.fromkeys([*DEFAULT_LANGUAGES, *(code for code in extra if code)]))


def get_preferred_language(lang: Optional[str]) -> str:
    """
    Tries to get default language from environment variables/ckan config, defaults to English
    """
    language = _normalize_language(lang)

    if not language:
        log.warning(
            "Could not determine preferred language from request headers, falling back to CKAN config"
        )
        language = _normalize_language(config.get("ckan.locale_default"))

    if language not in supported_languages():
        language = DEFAULT_FALLBACK_LANG

    return language


@dataclass(frozen=True)
class SchemaPlans:
    """What the schema of a dataset type says about the translation of its datasets, resources and their agents."""

    package: Dict[str, dict]
    resource: Dict[str, dict]
    package_agents: Dict[str, dict]
    resource_agents: Dict[str, dict]
    language_fields: frozenset


def plans_for(dataset_type: Optional[str]) -> SchemaPlans:
    """The plans of a dataset type, read from its schema (see ``schema_fields.translation_plan``)."""
    schema = schema_access.dataset_schema(dataset_type)
    dataset_fields = schema.get("dataset_fields") or []
    resource_fields = schema.get("resource_fields") or []
    package = {name: {"mark": {}, "children": {}} for name in CORE_TRANSLATED_FIELDS}
    package.update(schema_fields.translation_plan(dataset_fields))
    return SchemaPlans(
        package=package,
        resource=schema_fields.translation_plan(resource_fields),
        package_agents=schema_fields.agent_plan(dataset_fields),
        resource_agents=schema_fields.agent_plan(resource_fields),
        language_fields=frozenset(schema_fields.fluent_text_fields(dataset_fields, resource_fields)),
    )


def _collect_record(record: Dict, plan: Dict[str, dict], target_list: List) -> List:
    for name, node in plan.items():
        if name in record:
            target_list = _collect_value(record[name], node, target_list)
    return target_list


def _collect_value(value: Any, node: dict, target_list: List) -> List:
    """The values of a field that are looked up: all strings and numbers of a translated field, those of the
    translated subfields of a field that has some (the value of ``label_in`` field is looked up too)."""
    if value is None:
        return target_list
    if not node["children"]:
        return _append_atomic_value(value, target_list)

    for item in value if isinstance(value, list) else [value]:
        if isinstance(item, dict):
            target_list = _collect_record(item, node["children"], target_list)
        else:
            target_list = _append_atomic_value(item, target_list)
    return target_list


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
        plans = plans_for(package.get("type"))
        values_to_translate = _collect_record(package, plans.package, values_to_translate)
        for resource in package.get("resources", []):
            values_to_translate = _collect_record(resource, plans.resource, values_to_translate)
    return list(set(values_to_translate))


def collect_search_values_to_translate(result: Dict) -> List:
    """Values to translate for a package_search result: the labels used in the
    returned packages plus the value of every facet item (filter option)."""
    values_to_translate = collect_values_to_translate(result.get("results", []))
    for facet in result.get("search_facets", {}).values():
        values_to_translate.extend(
            item["name"] for item in facet.get("items", []) if "name" in item
        )
    return list(set(values_to_translate))


def replace_package(data, translation_dict, lang: Optional[str] = None):
    preferred_lang = get_preferred_language(lang)
    plans = plans_for(data.get("type"))

    _apply_translated_properties(data, preferred_lang, language_fields=plans.language_fields)
    _select_keywords_in_language(data, "tags", "tags_translated", preferred_lang)
    _normalize_tags_field(data)

    data = _translate_record(data, plans.package, translation_dict)
    resources = data.get("resources", [])

    for resource in resources:
        # a translated repeating field of a distribution (its access services) is a list, empty when it is absent
        resource = _translate_record(resource, plans.resource, translation_dict, absent_list=[])
        for access_service in resource.get("access_services") or []:
            _select_keywords_in_language(
                access_service, "keyword", "keyword_translated", preferred_lang
            )
    data["resources"] = resources
    _normalize_agent_identifiers(data, plans)

    return data


def _normalize_agent_identifiers(package: dict, plans: SchemaPlans) -> None:
    """
    Makes the identifier of every agent a list, also when the agent has no identifier,
    so that clients get one shape for all agents, whatever the way they were created.
    The fields that hold agents are the ones marked ``agent: true`` in the schema.
    """
    _normalize_agents_in(package, plans.package_agents)
    for resource in _dicts(package.get("resources")):
        _normalize_agents_in(resource, plans.resource_agents)


def _normalize_agents_in(record: dict, plan: Dict[str, dict]) -> None:
    for name, node in plan.items():
        for item in _dicts(record.get(name)):
            if node["mark"]:
                identifier = item.get("identifier")
                if identifier is None or identifier == "":
                    item["identifier"] = []
                elif not isinstance(identifier, list):
                    item["identifier"] = [identifier]
            _normalize_agents_in(item, node["children"])


def _dicts(values: Any) -> List[dict]:
    if isinstance(values, dict):
        return [values]
    return [value for value in values if isinstance(value, dict)] if isinstance(values, list) else []


def _keywords_of(values: Any) -> List[str]:
    if not isinstance(values, list):
        return []
    keywords = []
    for value in values:
        if isinstance(value, str) and value.strip() and value.strip() not in keywords:
            keywords.append(value.strip())
    return keywords


def _select_keywords_in_language(
    data: Any, field: str, translated_field: str, lang: str
) -> None:
    """
    Replace the keywords in `field` by the ones of `translated_field` in the preferred
    language, falling back to English and then to any language. `translated_field` is a
    multilingual dict like {"en": ["tag1"], "nl": ["tag2"]}. Without usable translations
    the plain keywords stay as they are.
    """
    if not isinstance(data, dict):
        return

    translated = data.get(translated_field)
    if not isinstance(translated, dict):
        return

    for code in (lang, DEFAULT_FALLBACK_LANG, *translated):
        keywords = _keywords_of(translated.get(code))
        if keywords:
            data[field] = keywords
            return


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


def _translate_record(record, plan, translation_dict, absent_list=None):
    """Show the fields of ``plan`` of a dataset or resource as ``{name, display_name}``.

    A planned field the record does not have is None (``absent_list`` for one that has translated subfields).
    """
    for field, node in plan.items():
        value = record.get(field)
        if value is None:
            record[field] = absent_list if node["children"] else None
        elif node["children"]:
            record[field] = _translate_nested(value, node, translation_dict)
        elif isinstance(value, List):
            record[field] = [
                ValueLabel(name=x, display_name=translation_dict.get(x, x)).__dict__
                for x in value
            ]
        else:
            record[field] = ValueLabel(
                name=value, display_name=translation_dict.get(value, value)
            ).__dict__
    return record


def _translate_nested(value: Any, node: dict, translation_dict: Dict[str, str]) -> Any:
    """Translate the subfields of a repeating field that ``translate`` marks (``node["children"]``)."""
    if isinstance(value, list):
        return [
            _translate_nested(item, node, translation_dict)
            if isinstance(item, (list, dict))
            else _translate_atomic_value(item, translation_dict)
            for item in value
        ]

    if isinstance(value, dict):
        if _is_value_label_dict(value):
            return value
        translated = value.copy()
        for name, child in node["children"].items():
            if name not in translated:
                continue
            if child["children"]:
                translated[name] = _translate_nested(translated[name], child, translation_dict)
            elif child["mark"].get("label_in"):
                _label_in(translated, name, child["mark"]["label_in"], translation_dict)
            else:
                translated[name] = _translate_atomic_or_collection(translated[name], translation_dict)
        return translated

    return _translate_atomic_value(value, translation_dict)


def _label_in(item: Dict, name: str, label_field: str, translation_dict: Dict[str, str]) -> None:
    """``translate: {label_in: label}``: the value stays the raw controlled-vocabulary URI, and ``label_field``
    is overwritten with its resolved display name (the URI itself when it has no translation), as the discovery
    API's ``dct_type``/``label`` contract wants."""
    value = item.get(name)
    if isinstance(value, str) and value:
        item[label_field] = translation_dict.get(value, value)


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


def _facet_sort_key(item):
    # CKAN core sorts facet items on the raw name, case-sensitive and in
    # reverse; sort on the translated label instead, ignoring case. Labels
    # that differ only in case order uppercase first (AaBbCc). That is decided
    # per character, so it also holds where the lowercase letter has the lower
    # code point (ß/ẞ, Georgian). The item name settles identical labels, so the
    # order does not depend on the order CKAN returned the items in.
    display_name = str(item["display_name"])
    uppercase_first = tuple(0 if char.lower() != char else 1 for char in display_name)
    return display_name.casefold(), uppercase_first, display_name, str(item.get("name", ""))


def replace_search_facets(data, translation_dict, lang):
    preferred_lang = get_preferred_language(lang)
    new_facets = {}
    for key, facet in data.items():
        title = facet["title"]
        new_facets[key] = {
            "title": get_translations([title], lang=preferred_lang).get(title, title)
        }
        new_facets[key]["items"] = sorted(
            (_change_facet(item, translation_dict) for item in facet["items"]),
            key=_facet_sort_key,
        )
    return new_facets


def _apply_translated_properties(
    data: Any,
    preferred_lang: str,
    fallback_lang: str = DEFAULT_FALLBACK_LANG,
    language_fields: frozenset = frozenset(),
):
    """Replace every ``<x>_translated`` dict, and every field of ``language_fields`` (the multilingual text fields
    of the schema), by its text in the preferred language, at any depth."""
    if not isinstance(data, (dict, list)):
        return data

    def apply(item):
        return _apply_translated_properties(item, preferred_lang, fallback_lang, language_fields)

    if isinstance(data, list):
        return [apply(item) if isinstance(item, (dict, list)) else item for item in data]

    for key, value in list(data.items()):
        if isinstance(value, dict):
            apply(value)
        elif isinstance(value, list):
            data[key] = [apply(item) if isinstance(item, (dict, list)) else item for item in value]

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
        elif key in language_fields and isinstance(value, dict):
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
