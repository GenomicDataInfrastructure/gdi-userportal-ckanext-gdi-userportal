from ckanext.gdi_userportal.logic.action.fetcher.prop_fetcher import PropFetcher


class DatasetFetcher(PropFetcher):
    def _get_batched_prop_values(self, batched_datasets):
        prop_name = "name"
        return [
            dataset[prop_name] for dataset in batched_datasets if prop_name in dataset
        ]
