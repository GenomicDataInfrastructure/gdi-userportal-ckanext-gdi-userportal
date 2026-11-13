# SPDX-FileCopyrightText: 2024 Stichting Health-RI
#
# SPDX-License-Identifier: Apache-2.0

"""
Initial vocabulary seed: the EU vocabulary translations from 001_initial_translations.csv.

Revision ID: 001_initial_seed
Revises: None (initial migration)
Create Date: 2026-01-27
"""

from typing import Union

# revision identifiers
revision: str = "001_initial_seed"
down_revision: Union[str, None] = None
description: str = "Seed EU vocabulary translations from 001_initial_translations.csv"


def upgrade() -> int:
    """Load all translations from the CSV seed file."""
    from ckanext.gdi_userportal.migrations.versions.term_translation_helpers import (
        load_csv, bulk_insert_translations
    )
    
    translations = load_csv("001_initial_translations.csv")
    return bulk_insert_translations(translations)


def downgrade() -> int:
    """Remove all translations loaded from the CSV seed file."""
    from ckanext.gdi_userportal.migrations.versions.term_translation_helpers import (
        load_csv, delete_translations_by_terms
    )
    
    translations = load_csv("001_initial_translations.csv")
    return delete_translations_by_terms(translations)
