# SPDX-FileCopyrightText: 2026 Stichting Health-RI
#
# SPDX-License-Identifier: Apache-2.0

"""
Add dataset-status and distribution-status translations

Revision ID: 007_status_translations
Revises: 006_typical_age_translation
Create Date: 2026-09-09 12:00:00
"""

from typing import Union

# revision identifiers
revision: str = "007_status_translations"
down_revision: Union[str, None] = "006_typical_age_translation"
description: str = "Add dataset-status and distribution-status translations"


def upgrade() -> int:
    """Apply the migration."""
    from ckanext.gdi_userportal.migrations.versions.term_translation_helpers import bulk_insert_translations, load_csv

    translations = load_csv("007_status_translations.csv")
    return bulk_insert_translations(translations)


def downgrade() -> int:
    """Revert the migration."""
    from ckanext.gdi_userportal.migrations.versions.term_translation_helpers import (
        delete_translations_by_terms,
        load_csv,
    )

    translations = load_csv("007_status_translations.csv")
    return delete_translations_by_terms(translations)
