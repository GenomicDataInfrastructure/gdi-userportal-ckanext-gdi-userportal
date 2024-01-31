# SPDX-FileCopyrightText: 2024 PNED G.I.E.
#
# SPDX-License-Identifier: Apache-2.0

from ckanext.gdi_userportal.logic.action.fetcher.prop_fetcher import PropFetcher


class PublisherFetcher(PropFetcher):
    @property
    def _prop_name(self) -> str:
        return "publisher_name"
