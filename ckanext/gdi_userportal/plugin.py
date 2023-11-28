import ckan.plugins as plugins
import ckan.plugins.toolkit as toolkit


class GdiUserPortalPlugin(plugins.SingletonPlugin):
    plugins.implements(plugins.IConfigurer)
    plugins.implements(plugins.IFacets, inherit=True)

    # IConfigurer

    def update_config(self, config_):
        toolkit.add_template_directory(config_, 'templates')
        toolkit.add_public_directory(config_, 'public')
        toolkit.add_resource('assets', 'ckanext-gdi-userportal')

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
