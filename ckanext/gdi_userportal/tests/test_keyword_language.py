# SPDX-FileCopyrightText: 2026 Stichting Health-RI
#
# SPDX-License-Identifier: Apache-2.0

"""Keywords of a dataset and of its access services follow the request language."""

import pytest

from ckanext.gdi_userportal.logic.action.translation_utils import replace_package

TRANSLATED = {"en": ["genomics", "health"], "nl": ["genomica", "gezondheid"]}


def _dataset(tags=None, tags_translated=None, keyword=None, keyword_translated=None):
    access_service = {}
    if keyword is not None:
        access_service["keyword"] = keyword
    if keyword_translated is not None:
        access_service["keyword_translated"] = keyword_translated
    package = {"resources": [{"access_services": [access_service]}]}
    if tags is not None:
        package["tags"] = tags
    if tags_translated is not None:
        package["tags_translated"] = tags_translated
    return package


def _tags(package, lang):
    return replace_package(package, {}, lang)["tags"]


def _keywords(package, lang):
    result = replace_package(package, {}, lang)
    return result["resources"][0]["access_services"][0]["keyword"]


class TestDatasetKeywords:
    def test_preferred_language_is_used(self):
        assert _tags(_dataset(tags_translated=TRANSLATED), "nl") == ["genomica", "gezondheid"]

    def test_region_suffix_of_the_language_is_ignored(self):
        assert _tags(_dataset(tags_translated=TRANSLATED), "nl-NL") == ["genomica", "gezondheid"]

    def test_unsupported_language_falls_back_to_english(self):
        assert _tags(_dataset(tags_translated=TRANSLATED), "fr") == ["genomics", "health"]

    def test_missing_preferred_language_falls_back_to_english(self):
        translated = {"en": ["genomics"], "nl": []}

        assert _tags(_dataset(tags_translated=translated), "nl") == ["genomics"]

    def test_any_language_is_used_when_neither_preferred_nor_english_exists(self):
        translated = {"de": ["genomik"]}

        assert _tags(_dataset(tags_translated=translated), "nl") == ["genomik"]

    def test_plain_tags_are_kept_without_translations(self):
        assert _tags(_dataset(tags=[{"name": "plain"}]), "nl") == ["plain"]

    def test_plain_tags_are_kept_when_all_translations_are_empty(self):
        package = _dataset(tags=["plain"], tags_translated={"en": [], "nl": [""]})

        assert _tags(package, "nl") == ["plain"]

    def test_other_languages_are_not_mixed_in(self):
        package = _dataset(tags=["genomics"], tags_translated=TRANSLATED)

        assert "genomics" not in _tags(package, "nl")

    def test_blank_and_duplicate_keywords_are_dropped(self):
        translated = {"nl": [" genomica ", "genomica", "", None]}

        assert _tags(_dataset(tags_translated=translated), "nl") == ["genomica"]


class TestMalformedTranslations:
    @pytest.mark.parametrize(
        "translated",
        ["not a dict", None, {"nl": "not a list"}, {"nl": [1, None, {"a": "b"}]}],
    )
    def test_plain_tags_are_kept(self, translated):
        package = _dataset(tags=["plain"], tags_translated=translated)

        assert _tags(package, "nl") == ["plain"]


class TestAccessServiceKeywords:
    def test_preferred_language_is_used(self):
        package = _dataset(keyword=["legacy"], keyword_translated=TRANSLATED)

        assert _keywords(package, "nl") == ["genomica", "gezondheid"]

    def test_unsupported_language_falls_back_to_english(self):
        package = _dataset(keyword=["legacy"], keyword_translated=TRANSLATED)

        assert _keywords(package, "fr") == ["genomics", "health"]

    def test_plain_keywords_are_kept_without_translations(self):
        assert _keywords(_dataset(keyword=["legacy"]), "nl") == ["legacy"]

    def test_every_access_service_of_every_resource_is_handled(self):
        package = {
            "resources": [
                {
                    "access_services": [
                        {"keyword_translated": {"en": ["one"], "nl": ["een"]}},
                        {"keyword_translated": {"en": ["two"], "nl": ["twee"]}},
                    ]
                },
                {"access_services": [{"keyword_translated": {"en": ["three"]}}]},
            ]
        }

        result = replace_package(package, {}, "nl")

        assert [
            service["keyword"]
            for resource in result["resources"]
            for service in resource["access_services"]
        ] == [["een"], ["twee"], ["three"]]

    @pytest.mark.parametrize("resources", [None, [], [{}], [{"access_services": None}]])
    def test_resources_without_access_services_are_left_alone(self, resources):
        package = {} if resources is None else {"resources": resources}

        replace_package(package, {}, "nl")
