# SPDX-FileCopyrightText: 2024 PNED G.I.E.
# SPDX-FileContributor: Stichting Health-RI
#
# SPDX-License-Identifier: Apache-2.0

import ckan.plugins as plugins
import ckan.plugins.toolkit as toolkit
from ckanext.gdi_userportal.logic.action.get import (
    get_catalogue_list,
    get_dataset_list,
    get_keyword_list,
    get_publisher_list,
    get_theme_list,
    scheming_package_show,
    get_with_url_labels,
)
from ckanext.gdi_userportal.logic.auth.get import config_option_show
import json


class GdiUserPortalPlugin(plugins.SingletonPlugin):
    plugins.implements(plugins.IConfigurer)
    plugins.implements(plugins.IFacets, inherit=True)
    plugins.implements(plugins.IAuthFunctions)
    plugins.implements(plugins.IActions)
    plugins.implements(plugins.IPackageController)

    # IConfigurer

    def update_config(self, config_):
        toolkit.add_template_directory(config_, "templates")
        toolkit.add_public_directory(config_, "public")
        toolkit.add_resource("assets", "ckanext-gdi-userportal")

        # IConfigurer

    def update_config_schema(self, schema):
        ignore_missing = toolkit.get_validator("ignore_missing")
        unicode_safe = toolkit.get_validator("unicode_safe")
        schema.update(
            {"ckanext.gdi_userportal.intro_text": [ignore_missing, unicode_safe]}
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
            "scheming_package_show": scheming_package_show,
            "theme_list": get_theme_list,
            "publisher_list": get_publisher_list,
            "keyword_list": get_keyword_list,
            "catalogue_list": get_catalogue_list,
            "dataset_list": get_dataset_list,
            "with_url_labels": get_with_url_labels,
        }

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

    def before_search(self, search_params):
        return search_params

    def after_search(self, search_results, search_params):
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

    def before_index(self, data_dict):
        fields = [
            "access_rights",
            "conforms_to",
            "has_version",
            "identifier",
            "language",
            "provenance",
            "publisher_name",
            "spatial_uri",
            "theme",
            "uri",
        ]
        for field in fields:
            data_dict = self._parse_to_array(data_dict, field)

        if data_dict.get("res_format"):
            data_dict["res_format"] = list(dict.fromkeys(data_dict.get("res_format")))

        return data_dict

    def before_view(self, pkg_dict):
        return pkg_dict

    def after_create(self, context, data_dict):
        return data_dict

    def after_update(self, context, data_dict):
        return data_dict

    def after_delete(self, context, data_dict):
        return data_dict

    def after_show(self, context, data_dict):
        return data_dict

    def update_facet_titles(self, facet_titles):
        return facet_titles
