# SPDX-FileCopyrightText: 2024 PNED G.I.E.
# SPDX-FileContributor: Stichting Health-RI
#
# SPDX-License-Identifier: Apache-2.0

import json
import ckan.plugins as plugins
import ckan.plugins.toolkit as toolkit
from ckanext.gdi_userportal.helpers import get_helpers as get_portal_helpers
from ckanext.gdi_userportal.logic.action.get import (
    enhanced_package_search,
    enhanced_package_show,
)
from ckanext.gdi_userportal.logic.auth.get import config_option_show
from ckanext.gdi_userportal.validation import scheming_isodatetime_flex

from opentelemetry import metrics
from opentelemetry.exporter.otlp.proto.http.metric_exporter import OTLPMetricExporter
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader
from opentelemetry.sdk.resources import SERVICE_NAME, Resource
from opentelemetry.instrumentation.flask import FlaskInstrumentor

from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor

import logging

log = logging.getLogger(__name__)


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
    plugins.implements(plugins.IPackageController)
    plugins.implements(plugins.IValidators)
    plugins.implements(plugins.ITemplateHelpers, inherit=True)
    plugins.implements(plugins.IMiddleware, inherit=True)
    plugins.implements(plugins.IConfigurable, inherit=True)
    plugins.implements(plugins.IClick)

    _dcatap_fields_to_normalize = [
        "access_rights",
        "conforms_to",
        "has_version",
        "language",
        "theme",
        "dcat_type",
        "code_values",
        "alternate_identifier",
        "documentation",
        "is_referenced_by",
        "analytics",
        "applicable_legislation",
        "coding_system",
        "purpose",
        "health_category",
        "health_theme",
        "legal_basis",
        "personal_data",
        "publisher_type",
    ]

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
        return facets_dict

    def dataset_facets(self, facets_dict, package_type):
        return self._update_facets(facets_dict)

    def group_facets(self, facets_dict, group_type, package_type):
        return self._update_facets(facets_dict)

    def organization_facets(self, facets_dict, organization_type, package_type):
        return self._update_facets(facets_dict)

        # IAuthFunctions

    def get_auth_functions(self):
        return {"config_option_show": config_option_show}

    def get_actions(self):
        return {
            "enhanced_package_search": enhanced_package_search,
            "enhanced_package_show": enhanced_package_show,
        }

    def get_helpers(self):
        return get_portal_helpers()

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
        return search_params

    def after_dataset_search(self, search_results, search_params):
        return search_results

    def _parse_to_array(self, data_dict, field):
        extras_field = f"extras_{field}"
        if data_dict.get(extras_field):
            try:
                data_dict[field] = json.loads(data_dict[extras_field])
            except json.JSONDecodeError:
                data_dict[field] = data_dict[extras_field]
            del data_dict[extras_field]
        return data_dict

    def _parse_agent_name(self, data_dict, field):
        if data_dict.get(field):
            values = data_dict[field]            
            if isinstance(values, str):
                try:
                    values = json.loads(values)
                except json.JSONDecodeError:
                    values = [{"name": values}]            
            if isinstance(values, dict):
                values = [values]
            
            names = list(set(value.get("name") for value in values if value.get("name")))
            data_dict[f"{field}_name"] = names
        return data_dict

    def before_dataset_index(self, data_dict):
        publisher_name = data_dict.get('extras_publisher__name')
        creator_name = data_dict.get('extras_creator__name')
        
        if publisher_name:
            try:
                publisher_names = json.loads(publisher_name)
                if isinstance(publisher_names, str):
                    publisher_names = [publisher_names]
            except json.JSONDecodeError:
                publisher_names = [publisher_name]
            data_dict['publisher_name'] = publisher_names
        
        if creator_name:
            try:
                creator_names = json.loads(creator_name)
                if isinstance(creator_names, str):
                    creator_names = [creator_names]
            except json.JSONDecodeError:
                creator_names = [creator_name]
            data_dict['creator_name'] = creator_names

        for field in self._dcatap_fields_to_normalize:
            data_dict = self._parse_to_array(data_dict, field)

        if data_dict.get("res_format"):
            data_dict["res_format"] = list(dict.fromkeys(data_dict.get("res_format")))

        data_dict = self._parse_agent_name(data_dict, "publisher")
        data_dict = self._parse_agent_name(data_dict, "creator")

        # Merge tags from tags_translated into tags for Solr indexing
        data_dict = self._merge_tags_translated_for_indexing(data_dict)

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

        # Get existing tags
        existing_tags = data_dict.get('tags', [])
        if isinstance(existing_tags, str):
            existing_tags = [existing_tags]

        # Collect all tags from tags_translated (all languages)
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
        return data_dict

    def update_facet_titles(self, facet_titles):
        return facet_titles

    def get_validators(self):
        return {"scheming_isodatetime_flex": scheming_isodatetime_flex}

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
