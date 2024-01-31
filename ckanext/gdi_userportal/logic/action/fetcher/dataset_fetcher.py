# SPDX-FileCopyrightText: 2024 PNED G.I.E.
#
# SPDX-License-Identifier: Apache-2.0

from ckanext.gdi_userportal.logic.action.fetcher.prop_fetcher import PropFetcher


class DatasetFetcher(PropFetcher):
    @property
    def _prop_name(self) -> str:
        return "name"
