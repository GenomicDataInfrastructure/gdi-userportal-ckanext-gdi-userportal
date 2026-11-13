# Term translation migrations

Versioned migrations load translations of controlled vocabulary terms into CKAN's `term_translation` table. A term is
usually a URI or a code; the translation is its label in one language. The labels are what the search index and the
API show for those terms (see the profile packs README, "What the API shows").

The module is `ckanext/gdi_userportal/migrations/`:

```
ckanext/gdi_userportal/migrations/
├── runner.py                        # Applies, rolls back and reports migrations
└── versions/
    ├── NNN_<name>.py                # One migration per file: revision, upgrade(), downgrade()
    ├── NNN_<name>.csv               # Optional seed data read by a migration
    └── term_translation_helpers.py  # load_csv, bulk_insert_translations, delete_translations_by_terms
```

The first migration, `001_initial_seed`, loads about 2,500 EU vocabulary labels from `001_initial_translations.csv`.

## How it runs

Migrations run when the CKAN container starts. `prerun.py` of gdi-userportal-ckan-docker (`run_term_translation_migrations`) runs
`ckan gdi-userportal translations migrate` after the CKAN database has been initialised or upgraded. It is skipped when
`gdi_userportal` is not in `CKAN__PLUGINS`.

- If the migration fails because the `term_translation` table does not exist yet, prerun runs `ckan db init` and
  `ckan db upgrade` and tries again.
- Otherwise it tries again after 3 seconds. After 10 failed attempts `prerun.py` exits with status 1, so the start
  fails and the error is in the container log.

Migrations are applied in version order, and each one runs once. They can also be run by hand.

## Tracking

Applied migrations are recorded in the `gdi_term_translation_migrations` table, which the runner creates:

| Column | Type | Description |
|--------|------|-------------|
| version | VARCHAR(255) | Migration version, for example `001_initial_seed` (primary key) |
| description | TEXT | Description of the migration |
| applied_at | TIMESTAMP | When the migration was applied |
| translations_added | INTEGER | Number of translations the migration wrote |

Writes are upserts: `INSERT ... ON CONFLICT (term, lang_code) DO UPDATE`. Existing rows are updated, not duplicated.
The runner adds the unique constraint on `term_translation (term, lang_code)` if it is missing.

## Commands

```bash
# Show which migrations are applied and which are pending
docker exec <ckan-container> ckan gdi-userportal translations status

# Apply all pending migrations (add --force to re-apply applied ones)
docker exec <ckan-container> ckan gdi-userportal translations migrate

# Show the content of one migration
docker exec <ckan-container> ckan gdi-userportal translations show 001_initial_seed

# Roll one migration back: removes the translations it wrote (asks unless -y is given)
docker exec <ckan-container> ckan gdi-userportal translations downgrade 001_initial_seed -y
```

## Deploying a change

- A new migration file is part of the image. Rebuild the image, or restart the container if the code is mounted.
- Restarting the container applies pending migrations, so no separate step is needed.
- Applied migrations are skipped. Changing the content of an already applied migration does not re-run it; use
  `translations migrate --force` on a test system, or write a new migration.
- A translation that is loaded reaches the free text of a dataset when that dataset is indexed again, so rebuild the
  search index after a migration that changes labels (`ckan search-index rebuild`).

## Creating a migration

Create the file with the next free number:

```bash
docker exec <ckan-container> ckan gdi-userportal translations create "Add terms for XYZ"
```

This writes `versions/NNN_<name>.py` from a template. Two ways to fill it in:

**Seed data in a CSV file** (for large sets). The file `versions/002_add_new_terms.csv` has the header `term,term_translation,lang_code`:

```csv
term,term_translation,lang_code
http://example.org/new-term,New Term,en
http://example.org/new-term,Nieuwe Term,nl
```

and `versions/002_add_new_terms.py` loads it:

```python
# SPDX-FileCopyrightText: 2024 Stichting Health-RI
# SPDX-License-Identifier: Apache-2.0

"""Add new vocabulary terms."""

from typing import Union

revision: str = "002_add_new_terms"
down_revision: Union[str, None] = "001_initial_seed"
description: str = "Add new vocabulary terms"


def upgrade() -> int:
    from ckanext.gdi_userportal.migrations.versions.term_translation_helpers import (
        load_csv, bulk_insert_translations
    )
    return bulk_insert_translations(load_csv("002_add_new_terms.csv"))


def downgrade() -> int:
    from ckanext.gdi_userportal.migrations.versions.term_translation_helpers import (
        load_csv, delete_translations_by_terms
    )
    return delete_translations_by_terms(load_csv("002_add_new_terms.csv"))
```

Commit both files and restart the container.

**Inline translations** (for small sets). Put the tuples in the migration file and pass the same list to the helpers
in `upgrade()` and `downgrade()`:

```python
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

| Symptom | Check |
|---------|-------|
| Migrations do not run at start | `gdi_userportal` is in `CKAN__PLUGINS`; the container log has the `[prerun]` lines. |
| Labels are missing from the API or from search | The terms are in `term_translation` for the language; the dataset was indexed after the migration (rebuild the index). |

Direct database access, when the CLI fails (the database service and the user come from the `.env` of
gdi-userportal-ckan-docker):

```bash
docker exec -it <db-container> psql -U <db-user> -d <db-name>

SELECT * FROM gdi_term_translation_migrations;
SELECT COUNT(*) FROM term_translation;
```

Deleting rows by hand is only for a test system: `DELETE FROM term_translation;` removes every translation, and the
migration table has to be cleared too for the migrations to run again.

## Tables

`term_translation` is CKAN's table:

| Column | Type | Description |
|--------|------|-------------|
| term | text | The term, usually a URI |
| term_translation | text | The label in `lang_code` |
| lang_code | text | Language code, for example `en` or `nl` |

Unique on `(term, lang_code)`.
