# SPDX-FileCopyrightText: 2024 Stichting Health-RI
#
# SPDX-License-Identifier: Apache-2.0

"""
Migration runner for term translations.

This module handles the execution of term translation migrations, including
version tracking, upgrade/downgrade operations, and idempotent application.

Uses an Alembic-like approach with versioned migration files in the versions/ directory.
"""

import importlib
import logging
import os
from typing import Any, Dict, List, Optional

from sqlalchemy import text
from ckan import model

log = logging.getLogger(__name__)

# Table to track applied migrations
MIGRATION_TABLE = "gdi_term_translation_migrations"


def _get_versions_path() -> str:
    """Get the path to the versions directory."""
    return os.path.join(os.path.dirname(__file__), "versions")


def _discover_versions() -> Dict[str, Any]:
    """
    Discover all migration versions from the versions/ directory.
    
    Returns:
        Dict mapping revision -> module
    """
    versions = {}
    versions_path = _get_versions_path()
    
    if not os.path.exists(versions_path):
        log.warning(f"Versions directory not found: {versions_path}")
        return versions
    
    for filename in os.listdir(versions_path):
        if filename.endswith(".py") and not filename.startswith("__"):
            module_name = filename[:-3]  # Remove .py
            try:
                module = importlib.import_module(
                    f"ckanext.gdi_userportal.migrations.versions.{module_name}"
                )
                if hasattr(module, "revision"):
                    versions[module.revision] = module
            except Exception as e:
                log.error(f"Failed to load migration version {module_name}: {e}")
    
    return versions


def _build_migration_order(versions: Dict[str, Any]) -> List[Any]:
    """
    Build the migration order by following the down_revision chain.
    
    Args:
        versions: Dict mapping revision -> module
        
    Returns:
        List of modules in order (oldest first)
    """
    if not versions:
        return []
    
    # Find the initial migration (down_revision is None)
    initial = None
    for rev, module in versions.items():
        if getattr(module, "down_revision", None) is None:
            initial = module
            break
    
    if initial is None:
        log.error("No initial migration found (down_revision = None)")
        return []
    
    # Build the chain
    ordered = [initial]
    current_rev = initial.revision
    
    # Build a reverse map: down_revision -> revision
    next_map = {}
    for rev, module in versions.items():
        down_rev = getattr(module, "down_revision", None)
        if down_rev is not None:
            next_map[down_rev] = module
    
    # Follow the chain
    while current_rev in next_map:
        next_module = next_map[current_rev]
        ordered.append(next_module)
        current_rev = next_module.revision
    
    return ordered


def _ensure_migration_table_exists():
    """Create the migration tracking table if it doesn't exist."""
    engine = model.meta.engine
    
    create_table_sql = text(f"""
        CREATE TABLE IF NOT EXISTS {MIGRATION_TABLE} (
            version VARCHAR(255) PRIMARY KEY,
            description TEXT,
            applied_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            translations_added INTEGER DEFAULT 0
        )
    """)
    
    with engine.begin() as conn:
        conn.execute(create_table_sql)


def _ensure_unique_constraint_exists():
    """Ensure the unique constraint exists on term_translation(term, lang_code)."""
    engine = model.meta.engine
    
    check_sql = text("""
        SELECT 1 FROM pg_constraint 
        WHERE conname = 'term_translation_term_lang_code_key'
    """)
    
    with engine.begin() as conn:
        result = conn.execute(check_sql)
        if result.fetchone():
            return
    
    try:
        with engine.begin() as conn:
            # Remove duplicates first
            dedup_sql = text("""
                DELETE FROM term_translation t1
                USING term_translation t2
                WHERE t1.ctid < t2.ctid
                AND t1.term = t2.term
                AND t1.lang_code = t2.lang_code
            """)
            conn.execute(dedup_sql)
            
            # Add unique constraint
            add_constraint_sql = text("""
                ALTER TABLE term_translation
                ADD CONSTRAINT term_translation_term_lang_code_key
                UNIQUE (term, lang_code)
            """)
            conn.execute(add_constraint_sql)
        log.info("Added unique constraint on term_translation(term, lang_code)")
    except Exception as e:
        log.warning(f"Could not add unique constraint (may already exist): {e}")


def _get_applied_migrations() -> List[str]:
    """Get list of already applied migration versions."""
    _ensure_migration_table_exists()
    engine = model.meta.engine
    
    query = text(f"SELECT version FROM {MIGRATION_TABLE} ORDER BY applied_at")
    
    with engine.begin() as conn:
        result = conn.execute(query)
        return [row[0] for row in result.fetchall()]


def _mark_migration_applied(version: str, description: str, count: int):
    """Mark a migration as applied in the tracking table."""
    engine = model.meta.engine
    
    insert_sql = text(f"""
        INSERT INTO {MIGRATION_TABLE} (version, description, translations_added)
        VALUES (:version, :description, :count)
        ON CONFLICT (version) DO UPDATE SET
            description = EXCLUDED.description,
            translations_added = EXCLUDED.translations_added,
            applied_at = CURRENT_TIMESTAMP
    """)
    
    with engine.begin() as conn:
        conn.execute(insert_sql, {"version": version, "description": description, "count": count})


def _mark_migration_removed(version: str):
    """Remove a migration from the tracking table (for downgrade)."""
    engine = model.meta.engine
    
    delete_sql = text(f"DELETE FROM {MIGRATION_TABLE} WHERE version = :version")
    
    with engine.begin() as conn:
        conn.execute(delete_sql, {"version": version})


def run_migrations(target_version: Optional[str] = None, force: bool = False) -> Dict:
    """
    Run all pending migrations up to the target version.
    
    Args:
        target_version: Optional version to migrate to. If None, applies all.
        force: If True, re-apply already applied migrations.
        
    Returns:
        Dictionary with migration results
    """
    _ensure_migration_table_exists()
    _ensure_unique_constraint_exists()
    
    versions = _discover_versions()
    ordered_migrations = _build_migration_order(versions)
    applied = set(_get_applied_migrations())
    
    results = {
        "applied": [],
        "skipped": [],
        "errors": [],
        "total_translations": 0,
    }
    
    for module in ordered_migrations:
        version = module.revision
        description = getattr(module, "description", "")
        
        # Stop if we've reached target version
        if target_version and version > target_version:
            break
        
        # Skip already applied migrations unless force is True
        if version in applied and not force:
            results["skipped"].append(version)
            log.debug(f"Skipping already applied migration: {version}")
            continue
        
        try:
            log.info(f"Applying migration: {version} - {description}")
            
            count = module.upgrade()
            _mark_migration_applied(version, description, count or 0)
            
            results["applied"].append(version)
            results["total_translations"] += count or 0
            
            log.info(f"Migration {version} applied successfully ({count} translations)")
            
        except Exception as e:
            log.error(f"Failed to apply migration {version}: {e}")
            results["errors"].append({"version": version, "error": str(e)})
    
    return results


def downgrade_migration(version: str) -> Dict:
    """
    Downgrade (remove) a specific migration.
    
    Args:
        version: The migration version to downgrade
        
    Returns:
        Dictionary with downgrade results
    """
    versions = _discover_versions()
    
    if version not in versions:
        return {"error": f"Migration {version} not found", "success": False}
    
    module = versions[version]
    results = {
        "version": version,
        "translations_removed": 0,
        "success": False,
    }
    
    try:
        log.info(f"Downgrading migration: {version}")
        
        count = module.downgrade()
        _mark_migration_removed(version)
        
        results["translations_removed"] = count or 0
        results["success"] = True
        
        log.info(f"Migration {version} downgraded successfully ({count} translations removed)")
        
    except Exception as e:
        log.error(f"Failed to downgrade migration {version}: {e}")
        results["error"] = str(e)
    
    return results


def get_current_version() -> Optional[str]:
    """Get the most recently applied migration version."""
    applied = _get_applied_migrations()
    return applied[-1] if applied else None


def get_migration_status() -> Dict:
    """
    Get the current status of all migrations.
    
    Returns:
        Dictionary with migration status information
    """
    _ensure_migration_table_exists()
    
    versions = _discover_versions()
    ordered_migrations = _build_migration_order(versions)
    applied = set(_get_applied_migrations())
    
    status = {
        "current_version": get_current_version(),
        "total_migrations": len(ordered_migrations),
        "applied_count": len(applied),
        "pending_count": len(ordered_migrations) - len(applied),
        "migrations": [],
    }
    
    for module in ordered_migrations:
        version = module.revision
        description = getattr(module, "description", "")
        
        status["migrations"].append({
            "version": version,
            "description": description,
            "applied": version in applied,
        })
    
    return status


def get_migration_by_version(version: str) -> Optional[Any]:
    """Get a migration module by its version."""
    versions = _discover_versions()
    return versions.get(version)
