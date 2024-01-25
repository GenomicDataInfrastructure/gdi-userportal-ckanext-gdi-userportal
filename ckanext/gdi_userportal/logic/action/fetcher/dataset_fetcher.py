from ckanext.gdi_userportal.logic.action.fetcher.prop_fetcher import PropFetcher


class DatasetFetcher(PropFetcher):
    @property
    def _prop_name(self) -> str:
        return "name"
