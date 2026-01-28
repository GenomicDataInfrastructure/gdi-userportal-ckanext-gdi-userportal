# Term Translation Migrations

This module provides an Alembic-like versioned migration system for managing term translations in CKAN's `term_translation` database table.

## Background

The original translations were part of the CKAN deployment until [PR #158](https://github.com/GenomicDataInfrastructure/gdi-userportal-ckan-docker/pull/158) (commit 4089575 - "Ckan 211") which removed them during the CKAN 2.11 upgrade. The removed files were:

- `ckan/docker-entrypoint.d/common_vocabulary_tags.csv` (~2400 translations)
- `ckan/docker-entrypoint.d/upload_vocabulary.sh` (shell script that ran on container startup)

This migration system restores that functionality with improvements:

| Old System | New Migration System |
|------------|---------------------|
| Shell script + CSV at container startup | Alembic-style versioned migrations |
| No version tracking | Tracks applied migrations in DB |
| Ran on every container start | Runs once per migration, idempotent |
| Direct psql commands | Uses SQLAlchemy with proper transactions |

## Directory Structure

```
ckanext/gdi_userportal/migrations/
├── __init__.py                      # Public API exports
├── runner.py                        # Migration execution engine
└── versions/                        # Migration files and data
    ├── __init__.py
    ├── 001_initial_seed.py          # Migration file
    ├── 001_initial_translations.csv # Seed data for 001 migration
    └── term_translation_helpers.py  # Reusable helper functions
```

## How It Works

### Automatic Execution on Container Startup

Migrations run **automatically** when the CKAN container starts via:

```
ckan/docker-entrypoint.d/03_run_translations_migrations.sh
```

**Startup sequence:**
1. Container starts
2. `prerun.py` runs (CKAN initialization)
3. `03_run_translations_migrations.sh` runs → `ckan gdi-userportal translations migrate`
4. Web server starts

**If migrations fail:** The container continues starting (non-blocking). You'll see a warning in logs but the service will be available.

### Migration Tracking

Applied migrations are tracked in the `gdi_term_translation_migrations` table:

| Column | Type | Description |
|--------|------|-------------|
| version | VARCHAR(255) | Migration version (e.g., "001_initial_seed") - PRIMARY KEY |
| description | TEXT | Human-readable description |
| applied_at | TIMESTAMP | When the migration was applied |
| translations_added | INTEGER | Count of translations added |

### Idempotency & Safety

- **Each migration runs only once** - tracked in the database
- **UPSERT operations** - existing translations are updated, not duplicated
- **Unique constraint** on `(term, lang_code)` prevents duplicates
- **Non-breaking** - if translations already exist, they're updated

## FAQ

### Do I need to run migrations manually?

**No.** Migrations run automatically on container startup. However, you can run them manually:

```bash
docker exec gdi-userportal-ckan-docker-ckan-dev-1 ckan gdi-userportal translations migrate
```

### Do I need to rebuild the container?

**Only if you add new migration files.** The migration code must be in the container for migrations to run.

- **New migrations added?** → Rebuild or restart container
- **Just deploying existing code?** → Container restart is enough

### Is this a breaking change?

**No.** The migration system is additive and non-breaking:

- If `term_translation` table is empty → translations are inserted
- If translations already exist → they're updated (UPSERT)
- If migration already applied → it's skipped

### What happens with an already running service?

When you deploy the new code and restart:

1. Container starts
2. Migration script runs automatically
3. Checks `gdi_term_translation_migrations` table
4. If `001_initial_seed` not applied → runs it (inserts ~2400 translations)
5. If already applied → skips it
6. Service continues normally

**No downtime, no data loss.**

## CLI Commands

```bash
# Check migration status
docker exec <ckan-container> ckan gdi-userportal translations status

# Run all pending migrations
docker exec <ckan-container> ckan gdi-userportal translations migrate

# Show details of a specific migration
docker exec <ckan-container> ckan gdi-userportal translations show 001_initial_seed

# Downgrade a specific migration (removes its translations)
docker exec <ckan-container> ckan gdi-userportal translations downgrade 001_initial_seed -y
```

## Creating New Migrations

### Manual Creation with CSV

For large translation sets, use a CSV file:

1. Create a new file in `versions/` with the next sequence number:

```python
# versions/002_add_new_terms.py

# SPDX-FileCopyrightText: 2024 Stichting Health-RI
# SPDX-License-Identifier: Apache-2.0

"""Add new vocabulary terms."""

from typing import Union

revision: str = "002_add_new_terms"
down_revision: Union[str, None] = "001_initial_seed"
description: str = "Add new vocabulary terms for XYZ"


def upgrade() -> int:
    from ckanext.gdi_userportal.migrations.versions.term_translation_helpers import (
        load_csv, bulk_insert_translations
    )
    translations = load_csv("002_new_terms.csv")
    return bulk_insert_translations(translations)


def downgrade() -> int:
    from ckanext.gdi_userportal.migrations.versions.term_translation_helpers import (
        load_csv, delete_translations_by_terms
    )
    translations = load_csv("002_new_terms.csv")
    return delete_translations_by_terms(translations)
```

2. Add the seed data file in `versions/002_new_terms.csv`:

```csv
term,term_translation,lang_code
http://example.org/new-term,New Term,en
http://example.org/new-term,Nieuwe Term,nl
```

3. Commit the files and rebuild/restart the container.

### Manual Creation with Inline Translations

For small translation sets:

```python
# versions/002_add_new_terms.py

from typing import Union, List, Tuple

revision: str = "002_add_new_terms"
down_revision: Union[str, None] = "001_initial_seed"
description: str = "Add new vocabulary terms"

TRANSLATIONS: List[Tuple[str, str, str]] = [
    ("my_field", "My Field", "en"),
    ("my_field", "Mijn Veld", "nl"),
]


def upgrade() -> int:
    from ckanext.gdi_userportal.migrations.versions.term_translation_helpers import bulk_insert_translations
    return bulk_insert_translations(TRANSLATIONS)


def downgrade() -> int:
    from ckanext.gdi_userportal.migrations.versions.term_translation_helpers import delete_translations_by_terms
    return delete_translations_by_terms(TRANSLATIONS)
```

## Troubleshooting

### Direct Database Access

If CLI commands fail, you can access the database directly:

```bash
# Connect to database
docker exec -it gdi-userportal-ckan-docker-db-1 psql -U ckandbuser -d ckandb

# Check applied migrations
SELECT * FROM gdi_term_translation_migrations;

# Count translations
SELECT COUNT(*) FROM term_translation;

# Clear translations (use with caution!)
DELETE FROM term_translation;
DELETE FROM gdi_term_translation_migrations;
```

### Common Issues

| Issue | Solution |
|-------|----------|
| "Cannot import 'run_migrations'" | Migration files not in container. Rebuild. |
| Migrations not running | Check `03_run_translations_migrations.sh` exists and is executable |
| Translations not showing | Check `term_translation` table has data; verify language codes match |

## Database Schema

### `term_translation` (CKAN Core Table)

| Column | Type | Description |
|--------|------|-------------|
| term | text | The original term (usually a URI) |
| term_translation | text | The translated value |
| lang_code | text | Language code (e.g., "en", "nl") |

**Unique constraint:** `(term, lang_code)`

### `gdi_term_translation_migrations` (Created by this module)

| Column | Type | Description |
|--------|------|-------------|
| version | VARCHAR(255) | Migration version identifier (PRIMARY KEY) |
| description | TEXT | Human-readable description |
| applied_at | TIMESTAMP | When applied |
| translations_added | INTEGER | Number of translations added |
