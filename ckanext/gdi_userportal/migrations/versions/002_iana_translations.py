# SPDX-FileCopyrightText: 2024 Stichting Health-RI
#
# SPDX-License-Identifier: Apache-2.0

"""
Add IANA translations

Revision ID: 002_iana_translations
Revises: 001_initial_seed
Create Date: 2026-02-24 11:14:06
"""

from typing import Union

# revision identifiers
revision: str = "002_iana_translations"
down_revision: Union[str, None] = "001_initial_seed"
description: str = "Add IANA translations"


def upgrade() -> int:
    """Apply the migration."""
    from ckanext.gdi_userportal.migrations.versions.term_translation_helpers import bulk_insert_translations, load_csv

    translations = load_csv("002_iana_translations.csv")
    return bulk_insert_translations(translations)


def downgrade() -> int:
    """Revert the migration."""
    from ckanext.gdi_userportal.migrations.versions.term_translation_helpers import (
        delete_translations_by_terms,
        load_csv,
    )

    translations = load_csv("002_iana_translations.csv")
    return delete_translations_by_terms(translations)
