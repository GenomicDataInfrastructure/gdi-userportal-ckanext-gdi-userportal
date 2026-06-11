# SPDX-FileCopyrightText: 2026 Health-RI
#
# SPDX-License-Identifier: Apache-2.0

from ckanext.gdi_userportal.logic.auth.get import gdi_filter_help_texts_show
from ckanext.gdi_userportal import plugin


def test_get_auth_functions_exposes_filter_help_texts_action():
    plugin_instance = plugin.GdiUserPortalPlugin()

    auth_functions = plugin_instance.get_auth_functions()

    assert auth_functions["gdi_filter_help_texts_show"] is gdi_filter_help_texts_show


def test_filter_help_texts_auth_allows_access():
    assert gdi_filter_help_texts_show(None, {}, {}) == {"success": True}
