# SPDX-FileCopyrightText: 2026 Health-RI
#
# SPDX-License-Identifier: Apache-2.0

from unittest.mock import MagicMock, patch

from ckanext.gdi_userportal.logic.action.get import enhanced_package_search

def _package_search_side_effect(min_value=None, max_value=None, main_result=None):
    def _side_effect(context, query):
        sort = query.get("sort", "")
        if sort.startswith("temporal_coverage_min"):
            docs = [{"temporal_coverage_min": min_value}] if min_value else []
            return {"results": docs, "count": len(docs)}
        if sort.startswith("temporal_coverage_max"):
            docs = [{"temporal_coverage_max": max_value}] if max_value else []
            return {"results": docs, "count": len(docs)}
        return dict(main_result) if main_result else {"results": [], "count": 0}

    return _side_effect


def _call(data_dict, min_value=None, max_value=None, main_result=None):
    package_search = MagicMock(
        side_effect=_package_search_side_effect(min_value, max_value, main_result)
    )
    with patch(
        "ckanext.gdi_userportal.logic.action.get.toolkit.get_action",
        return_value=package_search,
    ), patch(
        "ckanext.gdi_userportal.logic.action.get.collect_values_to_translate",
        return_value=[],
    ), patch(
        "ckanext.gdi_userportal.logic.action.get.get_request_language",
        return_value="en",
    ), patch(
        "ckanext.gdi_userportal.logic.action.get.get_translations",
        return_value={},
    ), patch(
        "ckanext.gdi_userportal.logic.action.get.replace_package",
        side_effect=lambda package, translations, lang: package,
    ):
        result = enhanced_package_search({}, data_dict)
    return result, package_search


class TestTemporalCoverageRangeStats:
    def test_stats_not_requested_by_default(self):
        result, package_search = _call({"q": "test"})
        assert package_search.call_count == 1
        assert "stats" not in result

    def test_stats_requested_for_unsupported_field_is_ignored(self):
        result, package_search = _call(
            {"stats": "true", "stats.field": '["some_other_field"]'}
        )
        assert package_search.call_count == 1
        assert "stats" not in result

    def test_stats_params_are_not_forwarded_to_solr(self):
        _, package_search = _call({"q": "test", "stats": "true", "stats.field": "[]"})
        main_query = package_search.call_args_list[0][0][1]
        assert "stats" not in main_query
        assert "stats.field" not in main_query

    def test_stats_requested_for_temporal_coverage_range_triggers_subqueries(self):
        result, package_search = _call(
            {"stats": "true", "stats.field": '["temporal_coverage_range"]'},
            min_value="2015-02-02T00:00:00Z",
            max_value="2024-12-31T00:00:00Z",
        )
        assert package_search.call_count == 3
        assert result["stats"] == {
            "stats_fields": {
                "temporal_coverage_range": {
                    "min": "2015-02-02T00:00:00Z",
                    "max": "2024-12-31T00:00:00Z",
                    "label": "temporal_coverage",
                }
            }
        }

    def test_subqueries_use_correct_sort_fl_rows_and_fq(self):
        _, package_search = _call(
            {"stats": "true", "stats.field": '["temporal_coverage_range"]'},
            min_value="2015-02-02T00:00:00Z",
            max_value="2024-12-31T00:00:00Z",
        )
        min_query = package_search.call_args_list[1][0][1]
        max_query = package_search.call_args_list[2][0][1]

        assert min_query["sort"] == "temporal_coverage_min asc"
        assert min_query["fl"] == ["temporal_coverage_min"]
        assert min_query["rows"] == 1
        assert "temporal_coverage_min:[* TO *]" in min_query["fq_list"]

        assert max_query["sort"] == "temporal_coverage_max desc"
        assert max_query["fl"] == ["temporal_coverage_max"]
        assert max_query["rows"] == 1
        assert "temporal_coverage_max:[* TO *]" in max_query["fq_list"]

    def test_subqueries_preserve_original_filters(self):
        _, package_search = _call(
            {
                "q": "flood",
                "ext_temporal_min": "2020-01-01",
                "stats": "true",
                "stats.field": '["temporal_coverage_range"]',
            },
            min_value="2015-02-02T00:00:00Z",
            max_value="2024-12-31T00:00:00Z",
        )
        min_query = package_search.call_args_list[1][0][1]
        assert min_query["q"] == "flood"
        assert min_query["ext_temporal_min"] == "2020-01-01"

    def test_no_stats_key_when_subqueries_return_no_results(self):
        result, _ = _call(
            {"stats": "true", "stats.field": '["temporal_coverage_range"]'}
        )
        assert "stats" not in result

    def test_label_uses_translated_temporal_coverage_term(self):
        package_search = MagicMock(
            side_effect=_package_search_side_effect(
                min_value="2015-02-02T00:00:00Z", max_value="2024-12-31T00:00:00Z"
            )
        )
        with patch(
            "ckanext.gdi_userportal.logic.action.get.toolkit.get_action",
            return_value=package_search,
        ), patch(
            "ckanext.gdi_userportal.logic.action.get.collect_values_to_translate",
            return_value=[],
        ), patch(
            "ckanext.gdi_userportal.logic.action.get.get_request_language",
            return_value="nl",
        ), patch(
            "ckanext.gdi_userportal.logic.action.get.get_translations",
            return_value={"temporal_coverage": "Temporele Dekking"},
        ) as get_translations, patch(
            "ckanext.gdi_userportal.logic.action.get.replace_package",
            side_effect=lambda package, translations, lang: package,
        ):
            result = enhanced_package_search(
                {}, {"stats": "true", "stats.field": '["temporal_coverage_range"]'}
            )

        assert (
            result["stats"]["stats_fields"]["temporal_coverage_range"]["label"]
            == "Temporele Dekking"
        )
        get_translations.assert_any_call(["temporal_coverage"], lang="nl")

    def test_stats_field_as_plain_list_is_accepted(self):
        result, package_search = _call(
            {"stats": True, "stats.field": ["temporal_coverage_range"]},
            min_value="2015-02-02T00:00:00Z",
            max_value="2024-12-31T00:00:00Z",
        )
        assert package_search.call_count == 3
        assert result["stats"]["stats_fields"]["temporal_coverage_range"] == {
            "min": "2015-02-02T00:00:00Z",
            "max": "2024-12-31T00:00:00Z",
            "label": "temporal_coverage",
        }
