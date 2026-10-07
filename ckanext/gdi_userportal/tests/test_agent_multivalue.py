# SPDX-FileCopyrightText: 2026 Stichting Health-RI
#
# SPDX-License-Identifier: Apache-2.0

"""Country and identifier of agents (publisher, creator, qualified attribution) hold several values."""

import json
from pathlib import Path

import pytest
import yaml

from ckanext.gdi_userportal import plugin
from ckanext.gdi_userportal.logic.action.translation_utils import (
    collect_values_to_translate,
    replace_package,
)

NLD = "http://publications.europa.eu/resource/authority/country/NLD"
DEU = "http://publications.europa.eu/resource/authority/country/DEU"
TRANSLATIONS = {NLD: "Netherlands", DEU: "Germany"}


def _label(uri):
    return {"name": uri, "display_name": TRANSLATIONS[uri], "count": None}


class TestSolrIndexing:
    def test_several_values_of_one_agent_are_all_indexed(self):
        data_dict = {
            "publisher": [
                {"name": "Org", "country": [NLD, DEU], "identifier": ["id-1", "id-2"]}
            ]
        }

        result = plugin.GdiUserPortalPlugin()._parse_agent_name(data_dict, "publisher")

        assert sorted(result["publisher_country"]) == sorted([NLD, DEU])
        assert sorted(result["publisher_identifier"]) == ["id-1", "id-2"]

    def test_lists_and_legacy_scalars_of_different_agents_are_merged_without_duplicates(
        self,
    ):
        data_dict = {
            "creator": [
                {"name": "Org 1", "country": [NLD, DEU], "identifier": ["id-1", "id-2"]},
                {"name": "Org 2", "country": NLD, "identifier": "id-3"},
            ]
        }

        result = plugin.GdiUserPortalPlugin()._parse_agent_name(data_dict, "creator")

        assert sorted(result["creator_country"]) == sorted([NLD, DEU])
        assert sorted(result["creator_identifier"]) == ["id-1", "id-2", "id-3"]

    def test_empty_lists_add_no_index_fields(self):
        data_dict = {"creator": [{"name": "Org", "country": [], "identifier": []}]}

        result = plugin.GdiUserPortalPlugin()._parse_agent_name(data_dict, "creator")

        assert "creator_country" not in result
        assert "creator_identifier" not in result

    def test_values_of_the_flat_extras_are_indexed_one_by_one(self):
        data_dict = {
            "extras_publisher__name": "Org",
            "extras_publisher__country": json.dumps([NLD, DEU]),
            "extras_publisher__identifier": "id-1",
        }

        result = plugin.GdiUserPortalPlugin()._parse_agent_name(data_dict, "publisher")

        assert result["publisher_name"] == ["Org"]
        assert sorted(result["publisher_country"]) == sorted([NLD, DEU])
        assert result["publisher_identifier"] == ["id-1"]


class TestReadTimeTranslation:
    @pytest.mark.parametrize("field", ["creator", "publisher"])
    def test_list_of_countries_becomes_a_list_of_labels(self, field):
        package = {field: [{"name": "Org", "country": [NLD, DEU], "identifier": ["a", "b"]}]}

        agent = replace_package(package, TRANSLATIONS, "en")[field][0]

        assert agent["country"] == [_label(NLD), _label(DEU)]
        assert agent["identifier"] == ["a", "b"]

    def test_legacy_scalar_country_is_still_resolved(self):
        package = {"creator": [{"name": "Org", "country": NLD, "identifier": "a"}]}

        agent = replace_package(package, TRANSLATIONS, "en")["creator"][0]

        assert agent["country"] == _label(NLD)
        assert agent["identifier"] == "a"

    def test_missing_and_empty_values_stay_as_they_are(self):
        package = {
            "creator": [{"name": "A"}, {"name": "B", "country": [], "identifier": []}]
        }

        agents = replace_package(package, TRANSLATIONS, "en")["creator"]

        assert "country" not in agents[0]
        assert agents[1]["country"] == [] and agents[1]["identifier"] == []

    def test_every_country_of_a_list_is_collected_for_translation(self):
        package = {
            "creator": [{"name": "Org", "country": [NLD, DEU]}],
            "publisher": [{"name": "Org", "country": [NLD]}],
        }

        values = collect_values_to_translate(package)

        assert NLD in values and DEU in values


class TestQualifiedAttributionAgentSchema:
    """A qualified attribution agent is an agent like a publisher or a creator."""

    SCHEMA = Path(plugin.__file__).parent / "scheming" / "schemas" / "dataset_multilingual.yaml"

    @staticmethod
    def _subfields(field):
        return [subfield["field_name"] for subfield in field["repeating_subfields"]]

    def _fields(self):
        schema = yaml.safe_load(self.SCHEMA.read_text())
        return {field["field_name"]: field for field in schema["dataset_fields"]}

    def test_qualified_attribution_agent_has_the_subfields_of_a_publisher_and_a_creator(self):
        fields = self._fields()
        agent = next(
            subfield
            for subfield in fields["qualified_attribution"]["repeating_subfields"]
            if subfield["field_name"] == "agent"
        )

        assert self._subfields(agent) == self._subfields(fields["publisher"])
        assert self._subfields(agent) == self._subfields(fields["creator"])

    def test_qualified_attribution_agent_stores_country_and_identifier(self):
        fields = self._fields()
        agent = next(
            subfield
            for subfield in fields["qualified_attribution"]["repeating_subfields"]
            if subfield["field_name"] == "agent"
        )

        assert {"country", "identifier"} <= set(self._subfields(agent))
