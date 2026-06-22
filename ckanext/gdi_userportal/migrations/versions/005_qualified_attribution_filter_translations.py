# SPDX-FileCopyrightText: 2026 Stichting Health-RI
#
# SPDX-License-Identifier: Apache-2.0

"""
Add qualified attribution filter translations

Revision ID: 005_qualified_attribution_filter_translations
Revises: 004_dataseries_filter_translations
Create Date: 2026-06-17 00:00:00
"""

from typing import List, Tuple, Union

# revision identifiers
revision: str = "005_qualified_attribution_filter_translations"
down_revision: Union[str, None] = "004_dataseries_filter_translations"
description: str = (
    "Add Dutch and English translations for qualified attribution filter labels"
)

TRANSLATIONS: List[Tuple[str, str, str]] = [
    (
        "vocab_qualified_attribution_role", 
        "Other responsible organisation role", 
        "en"
    ),
    (
        "vocab_qualified_attribution_role",
        "Overige verantwoordelijke organisatie rol",
        "nl",
    ),
    (
        "vocab_qualified_attribution_agent_name",
        "Other responsible organisation name",
        "en",
    ),
    (
        "vocab_qualified_attribution_agent_name",
        "Overige verantwoordelijke organisatie naam",
        "nl",
    ),
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
