# SPDX-FileCopyrightText: 2024 PNED G.I.E.
# SPDX-FileContributor: Stichting Health-RI
#
# SPDX-License-Identifier: Apache-2.0

import json
import os
from datetime import datetime
from urllib.parse import quote
from dateutil.parser import isoparse
import ckan.plugins as plugins
import ckan.plugins.toolkit as toolkit
from ckan import model
from ckanext.gdi_userportal.helpers import get_helpers as get_portal_helpers
from ckanext.gdi_userportal.languages import fall_back_to_available_languages
from ckanext.gdi_userportal import indexing, schema_access
from ckanext.gdi_userportal.logic.action.translation_utils import (
    SEARCH_INDEX_TRANSLATED_FIELDS,
    get_all_translations,
    _deduplicate_non_empty_strings,
)
from ckanext.gdi_userportal.validation import enforce_utc_time
from ckanext.gdi_userportal.temporal_coverage import (
    TEMPORAL_COVERAGE_RANGE_FIELD as TEMPORAL_COVERAGE_SOLR_FIELD,
    TEMPORAL_COVERAGE_MIN_FIELD,
    TEMPORAL_COVERAGE_MAX_FIELD,
    TEMPORAL_MIN_PARAM,
    TEMPORAL_MAX_PARAM,
)
from ckanext.gdi_userportal.logic.action.get import (
    gdi_dataset_help_texts_show,
    enhanced_package_search,
    enhanced_package_show,
    gdi_filter_help_texts_show,
    gdi_metadata_profile_conformance,
    gdi_metadata_profile_conformance_report,
)
from ckanext.gdi_userportal.logic.auth.get import (
    config_option_show,
    gdi_dataset_help_texts_show as gdi_dataset_help_texts_show_auth,
    gdi_filter_help_texts_show as gdi_filter_help_texts_show_auth,
    gdi_metadata_profile_conformance as gdi_metadata_profile_conformance_auth,
    gdi_metadata_profile_conformance_report as gdi_metadata_profile_conformance_report_auth,
    package_show as package_show_auth,
)
from ckanext.gdi_userportal import profile_visibility
from ckanext.gdi_userportal.validation import gdi_hex_binary, scheming_isodatetime_flex

from opentelemetry import metrics
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader
from opentelemetry.sdk.resources import SERVICE_NAME, Resource
from opentelemetry.instrumentation.flask import FlaskInstrumentor

from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor

import logging

log = logging.getLogger(__name__)

OTEL_EXPORTER_OTLP_PROTOCOL = os.getenv("OTEL_EXPORTER_OTLP_PROTOCOL", "http/protobuf").lower()
_ALLOWED_OTEL_EXPORTER_OTLP_PROTOCOLS = {"grpc", "http/protobuf"}

if OTEL_EXPORTER_OTLP_PROTOCOL not in _ALLOWED_OTEL_EXPORTER_OTLP_PROTOCOLS:
    log.warning(
        "Invalid OTEL_EXPORTER_OTLP_PROTOCOL=%r; falling back to 'http/protobuf'. "
        "Allowed values are: %s",
        OTEL_EXPORTER_OTLP_PROTOCOL,
        ", ".join(sorted(_ALLOWED_OTEL_EXPORTER_OTLP_PROTOCOLS)),
    )
    OTEL_EXPORTER_OTLP_PROTOCOL = "http/protobuf"

if OTEL_EXPORTER_OTLP_PROTOCOL == "grpc":
    from opentelemetry.exporter.otlp.proto.grpc.metric_exporter import OTLPMetricExporter
    from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
else:
    from opentelemetry.exporter.otlp.proto.http.metric_exporter import OTLPMetricExporter
    from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter

TRANSLATED_SEARCH_SOLR_FIELDS = {
    field_name: f"vocab_{field_name}_search"
    for field_name in SEARCH_INDEX_TRANSLATED_FIELDS
}
RESOURCE_TRANSLATED_SEARCH_FIELDS = ("conforms_to",)
RESOURCE_TRANSLATED_SEARCH_EXTRA_FIELDS = ("res_extras_conforms_to", "resource_conforms_to")
ACCESS_SERVICE_TRANSLATED_SEARCH_SOURCE = "res_extras_access_services"
PUBLICATIONS_DATA_THEME_HTTP_PREFIX = (
    "http://publications.europa.eu/resource/authority/data-theme/"  # NOSONAR - canonical authority URI
)
PUBLICATIONS_DATA_THEME_HTTPS_PREFIX = (
    "https://publications.europa.eu/resource/authority/data-theme/"
)

SOLR_DATETIME_FORMAT = "%Y-%m-%dT%H:%M:%SZ"


def setup_opentelemetry():
    resource = Resource(attributes={SERVICE_NAME: "ckan"})

    traceProvider = TracerProvider(resource=resource)
    processor = BatchSpanProcessor(OTLPSpanExporter())
    traceProvider.add_span_processor(processor)
    trace.set_tracer_provider(traceProvider)

    reader = PeriodicExportingMetricReader(OTLPMetricExporter())
    provider = MeterProvider(resource=resource, metric_readers=[reader])
    metrics.set_meter_provider(provider)


class GdiUserPortalPlugin(plugins.SingletonPlugin):
    plugins.implements(plugins.IConfigurer)
    plugins.implements(plugins.IFacets, inherit=True)
    plugins.implements(plugins.IAuthFunctions)
    plugins.implements(plugins.IActions)
    plugins.implements(plugins.IBlueprint)
    plugins.implements(plugins.IPackageController)
    plugins.implements(plugins.IValidators)
    plugins.implements(plugins.ITemplateHelpers, inherit=True)
    plugins.implements(plugins.IMiddleware, inherit=True)
    plugins.implements(plugins.IConfigurable, inherit=True)
    plugins.implements(plugins.IClick)

    # IConfigurer

    def update_config(self, config_):
        # Only override the header to add Harvest Sources to the nav.
        toolkit.add_template_directory(config_, "templates")

        # IConfigurer

    def update_config_schema(self, schema):
        ignore_missing = toolkit.get_validator("ignore_missing")
        unicode_safe = toolkit.get_validator("unicode_safe")
        int_validator = toolkit.get_validator("int_validator")
        schema.update(
            {
                "ckanext.gdi_userportal.intro_text": [ignore_missing, unicode_safe],
                "ckan.harvest.timeout": [ignore_missing, int_validator]
            }
        )
        return schema

    # IFacets

    def _update_facets(self, facets_dict):
        facets_dict.pop("groups", None)
        facets_dict["vocab_in_series_title"] = toolkit._("Dataset series")
        return facets_dict

    def dataset_facets(self, facets_dict, package_type):
        return self._update_facets(facets_dict)

    def group_facets(self, facets_dict, group_type, package_type):
        return self._update_facets(facets_dict)

    def organization_facets(self, facets_dict, organization_type, package_type):
        return self._update_facets(facets_dict)

    # IAuthFunctions

    def get_auth_functions(self):
        return {
            "config_option_show": config_option_show,
            "gdi_dataset_help_texts_show": gdi_dataset_help_texts_show_auth,
            "gdi_filter_help_texts_show": gdi_filter_help_texts_show_auth,
            "gdi_metadata_profile_conformance": gdi_metadata_profile_conformance_auth,
            "gdi_metadata_profile_conformance_report": gdi_metadata_profile_conformance_report_auth,
            "package_show": package_show_auth,
        }

    def get_actions(self):
        return {
            "enhanced_package_search": enhanced_package_search,
            "enhanced_package_show": enhanced_package_show,
            "gdi_dataset_help_texts_show": gdi_dataset_help_texts_show,
            "gdi_filter_help_texts_show": gdi_filter_help_texts_show,
            "gdi_metadata_profile_conformance": gdi_metadata_profile_conformance,
            "gdi_metadata_profile_conformance_report": gdi_metadata_profile_conformance_report,
        }

    def get_helpers(self):
        return get_portal_helpers()

    # IBlueprint
    def get_blueprint(self):
        """
        Ensure DCAT exports work for both datasets and dataset series without relying on
        HTTP redirects. Some clients (e.g. REST clients with redirect-following disabled)
        treat redirects as errors.
        """
        from ckanext.dcat.helpers import endpoints_enabled

        if not endpoints_enabled():
            return []

        from flask import Blueprint
        import ckanext.dcat.utils as dcat_utils

        bp = Blueprint("gdi_userportal_dcat_export_alias", __name__)

        def export_dataset_in_format(_id, _format):
            return dcat_utils.read_dataset_page(_id, _format)

        def view_for_format(_format):
            def view(_id):
                return export_dataset_in_format(_id, _format)

            return view

        for fmt in ("jsonld", "rdf", "ttl", "xml", "n3"):
            bp.add_url_rule(
                f"/dataset/<_id>.{fmt}",
                view_func=view_for_format(fmt),
                endpoint=f"export_dataset_{fmt}",
            )
            bp.add_url_rule(
                f"/dataset_series/<_id>.{fmt}",
                view_func=view_for_format(fmt),
                endpoint=f"export_dataset_series_{fmt}",
            )

        return [bp]

    def read(self, entity):
        pass

    def create(self, entity):
        pass

    def edit(self, entity):
        pass

    def authz_add_role(self, object_role):
        pass

    def authz_remove_role(self, object_role):
        pass

    def delete(self, entity):
        pass

    def before_dataset_search(self, search_params):
        # the datasets of a harvest source whose metadata profile is not enabled are not found
        enabled = profile_visibility.enabled_profiles(
            toolkit.config.get(profile_visibility.ENABLED_PROFILES_OPTION)
        )
        search_params = profile_visibility.hide_from_search(search_params, model.Session, enabled)

        extras = search_params.get("extras") or {}
        raw_min = extras.get(TEMPORAL_MIN_PARAM)
        raw_max = extras.get(TEMPORAL_MAX_PARAM)

        if not raw_min and not raw_max:
            return search_params

        min_value = self._to_solr_datetime(raw_min) if raw_min else None
        max_value = self._to_solr_datetime(raw_max) if raw_max else None

        if raw_min and min_value is None:
            raise toolkit.ValidationError(
                {TEMPORAL_MIN_PARAM: [toolkit._("Invalid date/time value")]}
            )
        if raw_max and max_value is None:
            raise toolkit.ValidationError(
                {TEMPORAL_MAX_PARAM: [toolkit._("Invalid date/time value")]}
            )
        if min_value and max_value and min_value > max_value:
            raise toolkit.ValidationError(
                {
                    TEMPORAL_MIN_PARAM: [
                        toolkit._(f"Must not be later than {TEMPORAL_MAX_PARAM}")
                    ]
                }
            )

        fq_list = list(search_params.get("fq_list") or [])
        fq_list.append(
            f"{TEMPORAL_COVERAGE_SOLR_FIELD}:[{min_value or '*'} TO {max_value or '*'}]"
        )
        search_params["fq_list"] = fq_list
        return search_params

    def after_dataset_search(self, search_results, search_params):
        return search_results

    def _to_solr_datetime(self, value):
        """Normalize a datetime (or ISO 8601 string) to a Solr-compatible UTC timestamp."""
        if isinstance(value, datetime):
            date = value
        elif value:
            try:
                date = isoparse(value)
            except (TypeError, ValueError):
                return None
        else:
            return None

        return enforce_utc_time(date).strftime(SOLR_DATETIME_FORMAT)

    def _build_temporal_coverage_ranges(self, data_dict):
        """Turn the temporal_coverage repeating field into Solr DateRangeField values.

        Each period becomes one entry of "[start TO end]" (using "*" for an
        open/missing bound) in a multiValued field, so a single Solr range query can
        match if it intersects *any* of a dataset's periods (the default operator for
        this field type is "Intersects"), and datasets without temporal_coverage simply
        have no value to match against.

        A missing start or end bound is intentionally treated as open-ended/ongoing
        (matches any date before/after the bound that is present), not as "unknown" -
        e.g. a period with a start but no end represents coverage that continues
        indefinitely and will intersect any filter range from that start date onward.

        Also populates temporal_coverage_min/_max: the earliest start and latest end
        across only the *bounded* periods (open bounds are skipped, since "*" has no
        finite value). Solr's Stats Component does not support DateRangeField, so
        these single-valued fields let enhanced_package_search compute a displayable
        min/max range via sorted queries instead.
        """
        raw_periods = data_dict.pop("temporal_coverage", None)
        if raw_periods is None:
            return data_dict

        if isinstance(raw_periods, str):
            try:
                raw_periods = json.loads(raw_periods)
            except json.JSONDecodeError:
                log.warning(
                    "Could not parse temporal_coverage as JSON, dropping value: %r",
                    raw_periods,
                )
                return data_dict

        if not isinstance(raw_periods, list):
            return data_dict

        ranges, bounded_starts, bounded_ends = self._parse_temporal_periods(raw_periods)

        if ranges:
            data_dict[TEMPORAL_COVERAGE_SOLR_FIELD] = ranges
        if bounded_starts:
            data_dict[TEMPORAL_COVERAGE_MIN_FIELD] = min(bounded_starts)
        if bounded_ends:
            data_dict[TEMPORAL_COVERAGE_MAX_FIELD] = max(bounded_ends)
        return data_dict

    def _parse_temporal_periods(self, raw_periods):
        """Build Solr range strings plus the bounded start/end values they contain."""
        ranges = []
        bounded_starts = []
        bounded_ends = []
        for period in raw_periods:
            if not isinstance(period, dict):
                continue
            start = self._to_solr_datetime(period.get("start"))
            end = self._to_solr_datetime(period.get("end"))
            if not start and not end:
                continue
            ranges.append(f"[{start or '*'} TO {end or '*'}]")
            if start:
                bounded_starts.append(start)
            if end:
                bounded_ends.append(end)
        return ranges, bounded_starts, bounded_ends

    def _parse_series_ids(self, in_series):
        if not in_series:
            return []

        if isinstance(in_series, list):
            return in_series

        if isinstance(in_series, str):
            try:
                parsed = json.loads(in_series)
            except json.JSONDecodeError:
                return [in_series]

            if isinstance(parsed, list):
                return parsed

            if parsed:
                return [parsed]

        return []

    def _extract_string_values(self, value):
        if value is None:
            return []

        if isinstance(value, str):
            return [item for item in indexing.values_of(value) if isinstance(item, str)]

        if isinstance(value, list):
            extracted = []
            for item in value:
                extracted.extend(self._extract_string_values(item))
            return extracted

        if isinstance(value, dict):
            extracted = []
            name = value.get("name")
            if isinstance(name, str):
                extracted.append(name)
            return extracted

        return []

    def _parse_json_if_possible(self, value):
        if not isinstance(value, str):
            return value

        try:
            return json.loads(value)
        except json.JSONDecodeError:
            return value

    def _canonicalize_publications_data_theme_uri(self, value):
        if not isinstance(value, str):
            return value

        if value.startswith(PUBLICATIONS_DATA_THEME_HTTPS_PREFIX):
            suffix = value[len(PUBLICATIONS_DATA_THEME_HTTPS_PREFIX) :]
            return f"{PUBLICATIONS_DATA_THEME_HTTP_PREFIX}{suffix}"

        return value

    def _normalize_theme_values(self, theme_value):
        if isinstance(theme_value, str):
            return self._canonicalize_publications_data_theme_uri(theme_value)

        if not isinstance(theme_value, list):
            return theme_value

        normalized = [
            self._canonicalize_publications_data_theme_uri(item)
            if isinstance(item, str)
            else item
            for item in theme_value
        ]

        deduplicated = []
        seen = set()
        for item in normalized:
            if isinstance(item, str):
                if item in seen:
                    continue
                seen.add(item)
            deduplicated.append(item)

        return deduplicated

    def _collect_resource_conforms_to_terms(self, data_dict):
        values = []

        for field_name in RESOURCE_TRANSLATED_SEARCH_EXTRA_FIELDS:
            values.extend(
                self._extract_string_values(
                    self._parse_json_if_possible(data_dict.get(field_name))
                )
            )

        resources = data_dict.get("resources")
        if isinstance(resources, list):
            for resource in resources:
                if not isinstance(resource, dict):
                    continue

                for field_name in RESOURCE_TRANSLATED_SEARCH_FIELDS:
                    values.extend(self._extract_string_values(resource.get(field_name)))

                access_services = resource.get("access_services")
                if isinstance(access_services, list):
                    for access_service in access_services:
                        if not isinstance(access_service, dict):
                            continue
                        values.extend(
                            self._extract_string_values(
                                access_service.get("conforms_to")
                            )
                        )

        access_services = self._parse_json_if_possible(
            data_dict.get(ACCESS_SERVICE_TRANSLATED_SEARCH_SOURCE)
        )
        if isinstance(access_services, list):
            for access_service in access_services:
                if not isinstance(access_service, dict):
                    continue
                values.extend(
                    self._extract_string_values(access_service.get("conforms_to"))
                )

        return _deduplicate_non_empty_strings(values)

    def _add_translated_search_fields(self, data_dict):
        field_terms = {}
        for field_name in SEARCH_INDEX_TRANSLATED_FIELDS:
            values = self._extract_string_values(data_dict.get(field_name))
            if field_name == "conforms_to":
                values.extend(self._collect_resource_conforms_to_terms(data_dict))
            field_terms[field_name] = values

        all_terms = []
        for values in field_terms.values():
            all_terms.extend(values)

        try:
            translations_by_term = get_all_translations(all_terms)
        except Exception:
            log.exception("Failed to load term translations for Solr indexing")
            translations_by_term = {}

        for field_name, solr_field in TRANSLATED_SEARCH_SOLR_FIELDS.items():
            search_terms = []
            for term in _deduplicate_non_empty_strings(field_terms[field_name]):
                search_terms.append(term)
                search_terms.extend(translations_by_term.get(term, []))

            search_terms = _deduplicate_non_empty_strings(search_terms)
            if search_terms:
                data_dict[solr_field] = search_terms

        return data_dict

    def _dataset_fields(self, data_dict):
        """The fields of the schema of this dataset type; none when the schema cannot be read."""
        return schema_access.dataset_fields(data_dict.get("type"))

    def before_dataset_index(self, data_dict):
        data_dict = self._build_temporal_coverage_ranges(data_dict)

        series_ids = self._parse_series_ids(data_dict.get("in_series"))
        if series_ids:
            data_dict["vocab_in_series"] = series_ids

            series_names = []
            series_titles = []

            for series_id in series_ids:
                try:
                    series_dict = toolkit.get_action("package_show")(
                        {"ignore_auth": True}, {"id": series_id}
                    )
                except (toolkit.ObjectNotFound, toolkit.NotAuthorized):
                    continue

                if series_dict.get("name"):
                    series_names.append(series_dict["name"])
                if series_dict.get("title"):
                    series_titles.append(series_dict["title"])

            if series_names:
                data_dict["vocab_in_series_name"] = list(
                    dict.fromkeys(series_names)
                )
            if series_titles:
                data_dict["vocab_in_series_title"] = list(
                    dict.fromkeys(series_titles)
                )

        # what is indexed under which Solr field follows the "solr" key of the fields in the schema (indexing.py)
        fields = self._dataset_fields(data_dict)
        data_dict = indexing.normalise_all(data_dict, fields)

        if data_dict.get("theme") is not None:
            data_dict["theme"] = self._normalize_theme_values(data_dict["theme"])

        if data_dict.get("res_format"):
            data_dict["res_format"] = list(dict.fromkeys(data_dict.get("res_format")))

        data_dict = indexing.flatten_all(data_dict, fields)

        data_dict = self._merge_tags_translated_for_indexing(data_dict)
        data_dict = self._add_translated_search_fields(data_dict)
        data_dict = indexing.keep_one_value_all(data_dict, fields)

        return data_dict

    def _merge_tags_translated_for_indexing(self, data_dict):
        """
        Merges tags from extras_tags_translated into the tags field for Solr indexing.
        This ensures manually added multilingual tags are searchable via tag filters.
        """
        tags_translated_raw = data_dict.get('extras_tags_translated')
        if not tags_translated_raw:
            return data_dict

        try:
            tags_translated = json.loads(tags_translated_raw) if isinstance(tags_translated_raw, str) else tags_translated_raw
        except json.JSONDecodeError:
            return data_dict

        if not isinstance(tags_translated, dict):
            return data_dict

        existing_tags = data_dict.get('tags', [])
        if isinstance(existing_tags, str):
            existing_tags = [existing_tags]

        seen = set(existing_tags)
        merged_tags = list(existing_tags)

        for lang_tags in tags_translated.values():
            if isinstance(lang_tags, list):
                for tag in lang_tags:
                    if isinstance(tag, str) and tag.strip() and tag.strip() not in seen:
                        seen.add(tag.strip())
                        merged_tags.append(tag.strip())

        data_dict['tags'] = merged_tags
        return data_dict

    def before_dataset_view(self, pkg_dict):
        return pkg_dict

    def after_dataset_create(self, context, data_dict):
        return data_dict

    def after_dataset_update(self, context, data_dict):
        return data_dict

    def after_dataset_delete(self, context, data_dict):
        return data_dict

    def after_dataset_show(self, context, data_dict):
        schema = toolkit.h.scheming_get_dataset_schema(data_dict.get("type", "dataset"))
        return fall_back_to_available_languages(data_dict, schema)

    def update_facet_titles(self, facet_titles):
        return facet_titles

    def get_validators(self):
        return {
            "scheming_isodatetime_flex": scheming_isodatetime_flex,
            "gdi_hex_binary": gdi_hex_binary,
        }

    # IConfigurable
    def configure(self, config):
        setup_opentelemetry()

    # IMiddleware
    def make_middleware(self, app, config):
        FlaskInstrumentor().instrument_app(app)
        return app

    # IClick
    def get_commands(self):
        from ckanext.gdi_userportal.cli import get_commands
        return get_commands()
