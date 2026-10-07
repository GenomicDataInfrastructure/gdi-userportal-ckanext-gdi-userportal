# SPDX-FileCopyrightText: 2026 Stichting Health-RI
#
# SPDX-License-Identifier: Apache-2.0

"""
Add translations for INSPIRE responsible party roles, IANA link relations and
SPDX checksum algorithms

Revision ID: 008_vocabulary_translations
Revises: 007_status_translations
Create Date: 2026-10-05 15:00:00
"""

from typing import Union

# revision identifiers
revision: str = "008_vocabulary_translations"
down_revision: Union[str, None] = "007_status_translations"
description: str = (
    "Add translations for INSPIRE responsible party roles, IANA link relations "
    "and SPDX checksum algorithms"
)


def upgrade() -> int:
    """Apply the migration."""
    from ckanext.gdi_userportal.migrations.versions.term_translation_helpers import bulk_insert_translations, load_csv

    translations = load_csv("008_vocabulary_translations.csv")
    return bulk_insert_translations(translations)


def downgrade() -> int:
    """Revert the migration."""
    from ckanext.gdi_userportal.migrations.versions.term_translation_helpers import (
        delete_translations_by_terms,
        load_csv,
    )

    translations = load_csv("008_vocabulary_translations.csv")
    return delete_translations_by_terms(translations)
