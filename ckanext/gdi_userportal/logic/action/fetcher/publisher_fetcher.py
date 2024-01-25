from ckanext.gdi_userportal.logic.action.fetcher.prop_fetcher import PropFetcher


class PublisherFetcher(PropFetcher):
    def _get_batched_prop_values(self, batched_datasets) -> list[str]:
        prop_name = "publisher_name"
        publishers = set(
            [dataset[prop_name] for dataset in batched_datasets if prop_name in dataset]
        )
        return publishers
