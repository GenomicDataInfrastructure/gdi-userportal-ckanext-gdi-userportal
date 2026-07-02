# SPDX-FileCopyrightText: 2026 Stichting Health-RI
#
# SPDX-License-Identifier: Apache-2.0

"""
Add Dutch and English translations for typical_age filter labels

Revision ID: 006_typical_age_translation
Revises: 005_qualified_attribution_filter_translations
Create Date: 2026-07-02 13:45:00
"""

from typing import List, Tuple, Union

# revision identifiers
revision: str = "006_typical_age_translation"
down_revision: Union[str, None] = "005_qualified_attribution_filter_translations"
description: str = (
    "Add Dutch and English translations for typical_age filter labels"
)

TRANSLATIONS: List[Tuple[str, str, str]] = [
    (
        "typical_age",
        "Age range",
        "en"
    ),
    (
        "typical_age",
        "Leeftijdbereik",
        "nl"
    )
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
