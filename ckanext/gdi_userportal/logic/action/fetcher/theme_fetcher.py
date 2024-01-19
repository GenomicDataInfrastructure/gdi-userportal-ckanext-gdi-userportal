import re
from functools import reduce

from ckanext.gdi_userportal.logic.action.fetcher.prop_fetcher import PropFetcher


class ThemeFetcher(PropFetcher):
    def _get_batched_prop_values(self, batched_datasets) -> list[str]:
        themes = [
            self._format_themes(dataset["theme"][0]) for dataset in batched_datasets
        ]
        themes = list(set(reduce(lambda themes1, themes2: themes1 + themes2, themes)))
        return themes

    @staticmethod
    def _format_themes(themes: list[str]) -> list[str]:
        if not themes:
            return [""]

        pattern = r'[\[\]" ]'
        return re.sub(pattern, "", themes).split(",")
