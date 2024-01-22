from abc import ABC, abstractmethod

from ckan.plugins import toolkit


class PropFetcher(ABC):
    def __init__(self, context, batch_size: int):
        self._context = context
        self._batch_size = batch_size

    def get_prop_list(self) -> dict[str, int | list[str]]:
        nb_datasets = self._get_dataset_count()
        prop_values = []

        for i in range((nb_datasets // self._batch_size) + 1):
            batched_datasets = self._fetch_batched_datasets(
                self._batch_size * i, self._batch_size
            )
            batched_prop_values = self._get_batched_prop_values(batched_datasets)
            prop_values.extend(batched_prop_values)

        return {"count": len(prop_values), "results": prop_values}

    def _get_dataset_count(self) -> int:
        return toolkit.get_action("package_search")(
            self._context, {"include_private": False}
        )["count"]

    def _fetch_batched_datasets(self, start_row: int, nb_rows: int) -> list[dict]:
        datasets = toolkit.get_action("package_search")(
            self._context,
            {"include_private": False, "start": start_row, "rows": nb_rows},
        )["results"]
        return datasets

    @abstractmethod
    def _get_batched_prop_values(self, batched_datasets: list[dict]) -> list[str]:
        pass
