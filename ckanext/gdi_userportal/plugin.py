import ckan.plugins as plugins
import ckan.plugins.toolkit as toolkit
import ckanext.gdi_userportal.logic.auth.get as auth_get
import ckanext.gdi_userportal.logic.action.get as action_get


class GdiUserPortalPlugin(plugins.SingletonPlugin):
    plugins.implements(plugins.IConfigurer)
    plugins.implements(plugins.IFacets, inherit=True)
    plugins.implements(plugins.IAuthFunctions)
    plugins.implements(plugins.IActions)
    
    # IConfigurer

    def update_config(self, config_):
        toolkit.add_template_directory(config_, "templates")
        toolkit.add_public_directory(config_, "public")
        toolkit.add_resource("assets", "ckanext-gdi-userportal")
    
        # IConfigurer
    def update_config_schema(self, schema):
        ignore_missing = toolkit.get_validator('ignore_missing')
        unicode_safe = toolkit.get_validator('unicode_safe')
        schema.update({
            'ckanext.gdi_userportal.intro_text': [ignore_missing, unicode_safe]
        })
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
        return {
            'config_option_show': auth_get.config_option_show
        }

    def get_actions(self):
        return {
            'scheming_package_show': action_get.scheming_package_show
        }