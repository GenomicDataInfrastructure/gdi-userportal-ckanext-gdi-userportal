# SPDX-FileCopyrightText: 2024 Stichting Health-RI
#
# SPDX-License-Identifier: Apache-2.0

"""
Initial vocabulary seed - restore translations from initial_translations.csv

This migration restores the EU vocabulary translations that were removed in PR #158
(commit 4089575 - "Ckan 211") during the CKAN 2.11 upgrade.

PR #158: https://github.com/GenomicDataInfrastructure/gdi-userportal-ckan-docker/pull/158

Revision ID: 001_initial_seed
Revises: None (initial migration)
Create Date: 2026-01-27
"""

from typing import Union

# revision identifiers
revision: str = "001_initial_seed"
down_revision: Union[str, None] = None
description: str = "Restore EU vocabulary translations from initial_translations.csv (removed in PR #158)"


def upgrade() -> int:
    """Load all translations from the CSV seed file."""
    from ckanext.gdi_userportal.migrations.base import load_csv, bulk_insert_translations
    
    translations = load_csv("initial_translations.csv")
    return bulk_insert_translations(translations)


def downgrade() -> int:
    """Remove all translations loaded from the CSV seed file."""
    from ckanext.gdi_userportal.migrations.base import load_csv, delete_translations_by_terms
    
    translations = load_csv("initial_translations.csv")
    return delete_translations_by_terms(translations)
