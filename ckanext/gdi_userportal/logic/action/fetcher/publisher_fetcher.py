from ckanext.gdi_userportal.logic.action.fetcher.prop_fetcher import PropFetcher


class PublisherFetcher(PropFetcher):
    def _get_batched_prop_values(self, batched_datasets) -> list[str]:
        publishers = set([dataset["publisher_name"] for dataset in batched_datasets])
        return publishers
