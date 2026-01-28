# SPDX-FileCopyrightText: 2024 Stichting Health-RI
#
# SPDX-License-Identifier: Apache-2.0

"""
Base utilities for term translation migrations.

Provides helper functions for loading seed data and executing
database operations in migration files.
"""

import csv
import logging
import os
from typing import List, Tuple

from sqlalchemy import text
from ckan import model

log = logging.getLogger(__name__)


def get_seeds_path() -> str:
    """Get the path to the seeds directory."""
    return os.path.join(os.path.dirname(__file__), "seeds")


def load_csv(filename: str) -> List[Tuple[str, str, str]]:
    """
    Load translations from a CSV file in the seeds directory.
    
    Args:
        filename: Name of the CSV file (e.g., "initial_translations.csv")
        
    Returns:
        List of (term, translation, lang_code) tuples
    """
    csv_path = os.path.join(get_seeds_path(), filename)
    translations = []
    
    with open(csv_path, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            term = row.get("term", "").strip()
            translation = row.get("term_translation", "").strip()
            lang_code = row.get("lang_code", "").strip()
            if term and translation and lang_code:
                translations.append((term, translation, lang_code))
    
    log.info(f"Loaded {len(translations)} translations from {filename}")
    return translations


def bulk_insert_translations(translations: List[Tuple[str, str, str]]) -> int:
    """
    Insert or update translations in the term_translation table.
    
    Uses UPSERT (INSERT ... ON CONFLICT DO UPDATE) for efficiency.
    
    Args:
        translations: List of (term, translation, lang_code) tuples
        
    Returns:
        Number of translations applied
    """
    if not translations:
        return 0
    
    engine = model.meta.engine
    
    upsert_sql = text("""
        INSERT INTO term_translation (term, term_translation, lang_code)
        VALUES (:term, :translation, :lang_code)
        ON CONFLICT (term, lang_code) DO UPDATE SET
            term_translation = EXCLUDED.term_translation
    """)
    
    count = 0
    with engine.begin() as conn:
        for term, translation, lang_code in translations:
            try:
                conn.execute(upsert_sql, {
                    "term": term,
                    "translation": translation,
                    "lang_code": lang_code
                })
                count += 1
            except Exception as e:
                log.error(f"Failed to insert translation for '{term}' ({lang_code}): {e}")
    
    log.info(f"Inserted/updated {count} translations")
    return count


def bulk_delete_translations(removals: List[Tuple[str, str]]) -> int:
    """
    Delete translations from the term_translation table.
    
    Args:
        removals: List of (term, lang_code) tuples to remove
        
    Returns:
        Number of translations removed
    """
    if not removals:
        return 0
    
    engine = model.meta.engine
    
    delete_sql = text("""
        DELETE FROM term_translation
        WHERE term = :term AND lang_code = :lang_code
    """)
    
    count = 0
    with engine.begin() as conn:
        for term, lang_code in removals:
            try:
                result = conn.execute(delete_sql, {
                    "term": term,
                    "lang_code": lang_code
                })
                count += result.rowcount
            except Exception as e:
                log.error(f"Failed to delete translation for '{term}' ({lang_code}): {e}")
    
    log.info(f"Deleted {count} translations")
    return count


def delete_translations_by_terms(translations: List[Tuple[str, str, str]]) -> int:
    """
    Delete translations based on the translations list (for downgrade).
    
    Args:
        translations: List of (term, translation, lang_code) tuples
        
    Returns:
        Number of translations removed
    """
    removals = [(term, lang_code) for term, _, lang_code in translations]
    return bulk_delete_translations(removals)
