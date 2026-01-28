# SPDX-FileCopyrightText: 2024 Stichting Health-RI
#
# SPDX-License-Identifier: Apache-2.0

"""
Term translation migrations for GDI User Portal CKAN extension.

This module provides an Alembic-like versioned migration system for managing
term_translation entries in the CKAN database.

Structure:
- versions/      Individual migration files (001_xxx.py, 002_xxx.py, etc.)
- seeds/         Seed data files (CSV, JSON, etc.)
- base.py        Helper functions for migrations
- runner.py      Migration execution engine

Each version file has:
- revision: Unique version identifier
- down_revision: Previous version (None for initial)
- description: Human-readable description
- upgrade(): Function to apply the migration
- downgrade(): Function to revert the migration

Usage:
    # Run all pending migrations
    from ckanext.gdi_userportal.migrations import run_migrations
    run_migrations()
    
    # Check status
    from ckanext.gdi_userportal.migrations import get_migration_status
    status = get_migration_status()
"""

from ckanext.gdi_userportal.migrations.runner import (
    run_migrations,
    downgrade_migration,
    get_current_version,
    get_migration_status,
    get_migration_by_version,
)

__all__ = [
    "run_migrations",
    "downgrade_migration",
    "get_current_version",
    "get_migration_status",
    "get_migration_by_version",
]
