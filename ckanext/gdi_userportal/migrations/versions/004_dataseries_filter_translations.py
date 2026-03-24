# SPDX-FileCopyrightText: 2026 Stichting Health-RI
#
# SPDX-License-Identifier: Apache-2.0

"""
Add dataset series filter translations

Revision ID: 004_dataseries_filter_translations
Revises: 003_missing_healthdcatap_translations
Create Date: 2026-03-23 15:02:00
"""

from typing import List, Tuple, Union

# revision identifiers
revision: str = "004_dataseries_filter_translations"
down_revision: Union[str, None] = "003_missing_healthdcatap_translations"
description: str = "Add Dutch and English translations for the dataset series filter"

TRANSLATIONS: List[Tuple[str, str, str]] = [
    ("vocab_in_series_title", "Dataset series", "en"),
    ("vocab_in_series_title", "Dataset reeks", "nl"),
]


def upgrade() -> int:
    """Apply the migration."""
    from ckanext.gdi_userportal.migrations.versions.term_translation_helpers import (
        bulk_insert_translations,
    )

    return bulk_insert_translations(TRANSLATIONS)


def downgrade() -> int:
    """Revert the migration."""
    from ckanext.gdi_userportal.migrations.versions.term_translation_helpers import (
        delete_translations_by_terms,
    )

    return delete_translations_by_terms(TRANSLATIONS)
