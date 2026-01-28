# SPDX-FileCopyrightText: 2024 Stichting Health-RI
#
# SPDX-License-Identifier: Apache-2.0

"""
CLI commands for GDI User Portal CKAN extension.
"""

import click
import json
import os
from datetime import datetime


@click.group()
def gdi_userportal():
    """GDI User Portal management commands."""
    pass


@gdi_userportal.group()
def translations():
    """Term translation migration commands."""
    pass


@translations.command("migrate")
@click.option("--target", "-t", default=None, help="Target migration version")
@click.option("--force", "-f", is_flag=True, help="Force re-apply all migrations")
def migrate(target, force):
    """Run pending term translation migrations."""
    from ckanext.gdi_userportal.migrations import run_migrations
    
    click.echo("Running term translation migrations...")
    
    try:
        results = run_migrations(target_version=target, force=force)
        
        if results["applied"]:
            click.echo(click.style(f"\n✓ Applied {len(results['applied'])} migration(s):", fg="green"))
            for version in results["applied"]:
                click.echo(f"  - {version}")
            click.echo(f"\nTotal translations added/updated: {results['total_translations']}")
        
        if results["skipped"]:
            click.echo(click.style(f"\n⊘ Skipped {len(results['skipped'])} already applied migration(s)", fg="yellow"))
        
        if results["errors"]:
            click.echo(click.style(f"\n✗ Errors in {len(results['errors'])} migration(s):", fg="red"))
            for error in results["errors"]:
                click.echo(f"  - {error['version']}: {error['error']}")
        
        if not results["applied"] and not results["errors"]:
            click.echo(click.style("\n✓ All migrations already applied. Database is up to date.", fg="green"))
            
    except Exception as e:
        click.echo(click.style(f"\n✗ Migration failed: {e}", fg="red"))
        raise click.Abort()


@translations.command("status")
@click.option("--json", "as_json", is_flag=True, help="Output as JSON")
def status(as_json):
    """Show term translation migration status."""
    from ckanext.gdi_userportal.migrations import get_migration_status
    
    try:
        migration_status = get_migration_status()
        
        if as_json:
            click.echo(json.dumps(migration_status, indent=2))
            return
        
        click.echo("\n=== Term Translation Migration Status ===\n")
        click.echo(f"Current version: {migration_status['current_version'] or 'None'}")
        click.echo(f"Total migrations: {migration_status['total_migrations']}")
        click.echo(f"Applied: {migration_status['applied_count']}")
        click.echo(f"Pending: {migration_status['pending_count']}")
        
        click.echo("\n--- Migrations ---")
        for m in migration_status["migrations"]:
            status_icon = click.style("✓", fg="green") if m["applied"] else click.style("○", fg="yellow")
            click.echo(f"  {status_icon} {m['version']}")
            click.echo(f"      {m['description']}")
            
    except Exception as e:
        click.echo(click.style(f"\n✗ Failed to get status: {e}", fg="red"))
        raise click.Abort()


@translations.command("downgrade")
@click.argument("version")
@click.option("--yes", "-y", is_flag=True, help="Skip confirmation")
def downgrade(version, yes):
    """Downgrade (remove) a specific migration."""
    from ckanext.gdi_userportal.migrations import downgrade_migration, get_migration_by_version
    
    module = get_migration_by_version(version)
    if not module:
        click.echo(click.style(f"✗ Migration '{version}' not found", fg="red"))
        raise click.Abort()
    
    description = getattr(module, "description", "")
    
    if not yes:
        click.echo(f"\nAbout to downgrade migration: {version}")
        click.echo(f"Description: {description}")
        
        if not click.confirm("\nAre you sure you want to proceed?"):
            click.echo("Aborted.")
            return
    
    try:
        results = downgrade_migration(version)
        
        if results.get("success"):
            click.echo(click.style(f"\n✓ Migration {version} downgraded successfully", fg="green"))
            click.echo(f"Translations removed: {results['translations_removed']}")
        else:
            click.echo(click.style(f"\n✗ Downgrade failed: {results.get('error', 'Unknown error')}", fg="red"))
            
    except Exception as e:
        click.echo(click.style(f"\n✗ Downgrade failed: {e}", fg="red"))
        raise click.Abort()


@translations.command("create")
@click.argument("description")
def create(description):
    """Create a new migration version file.
    
    Example: ckan gdi-userportal translations create "add country translations"
    """
    from ckanext.gdi_userportal.migrations import get_migration_status
    
    try:
        # Get current status to determine next version number
        status = get_migration_status()
        migrations = status.get("migrations", [])
        
        if migrations:
            # Get the last version number and increment
            last_version = migrations[-1]["version"]
            try:
                last_num = int(last_version.split("_")[0])
                next_num = last_num + 1
            except (ValueError, IndexError):
                next_num = len(migrations) + 1
            down_revision = last_version
        else:
            next_num = 1
            down_revision = None
        
        # Create filename
        slug = description.lower().replace(" ", "_").replace("-", "_")
        slug = "".join(c for c in slug if c.isalnum() or c == "_")[:50]
        version = f"{next_num:03d}"
        filename = f"{version}_{slug}.py"
        
        # Get versions directory path
        versions_dir = os.path.join(
            os.path.dirname(__file__),
            "migrations", "versions"
        )
        filepath = os.path.join(versions_dir, filename)
        
        # Generate migration content
        down_rev_str = f'"{down_revision}"' if down_revision else "None"
        content = f'''# SPDX-FileCopyrightText: 2024 Stichting Health-RI
#
# SPDX-License-Identifier: Apache-2.0

"""
{description}

Revision ID: {version}
Revises: {down_revision or 'None'}
Create Date: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
"""

from typing import Union, List, Tuple

# revision identifiers
revision: str = "{version}"
down_revision: Union[str, None] = {down_rev_str}
description: str = "{description}"


# Define your translations here
# Format: (term, translation, lang_code)
TRANSLATIONS: List[Tuple[str, str, str]] = [
    # Example:
    # ("my_field", "My Field", "en"),
    # ("my_field", "Mijn Veld", "nl"),
]


def upgrade() -> int:
    """Apply the migration."""
    from ckanext.gdi_userportal.migrations.base import bulk_insert_translations
    return bulk_insert_translations(TRANSLATIONS)


def downgrade() -> int:
    """Revert the migration."""
    from ckanext.gdi_userportal.migrations.base import delete_translations_by_terms
    return delete_translations_by_terms(TRANSLATIONS)
'''
        
        # Write the file
        with open(filepath, "w") as f:
            f.write(content)
        
        click.echo(click.style(f"\n✓ Created new migration:", fg="green"))
        click.echo(f"  Version: {version}")
        click.echo(f"  File: {filename}")
        click.echo(f"  Path: {filepath}")
        click.echo(f"\nEdit the TRANSLATIONS list in the file to add your translations.")
        
    except Exception as e:
        click.echo(click.style(f"\n✗ Failed to create migration: {e}", fg="red"))
        raise click.Abort()


@translations.command("show")
@click.argument("version")
def show(version):
    """Show details of a specific migration."""
    from ckanext.gdi_userportal.migrations import get_migration_by_version
    
    module = get_migration_by_version(version)
    
    if not module:
        click.echo(click.style(f"✗ Migration '{version}' not found", fg="red"))
        raise click.Abort()
    
    click.echo(f"\n=== Migration: {module.revision} ===\n")
    click.echo(f"Description: {getattr(module, 'description', 'N/A')}")
    click.echo(f"Down revision: {getattr(module, 'down_revision', None) or 'None (initial)'}")
    
    # Try to get translations if available
    if hasattr(module, "TRANSLATIONS"):
        translations = module.TRANSLATIONS
        click.echo(f"Translations: {len(translations)}")
        
        click.echo("\n--- Sample Translations ---")
        by_lang = {}
        for term, translation, lang in translations[:20]:  # Show first 20
            if lang not in by_lang:
                by_lang[lang] = []
            by_lang[lang].append((term, translation))
        
        for lang, items in sorted(by_lang.items()):
            click.echo(f"\n  [{lang.upper()}]")
            for term, translation in items[:5]:  # Show first 5 per language
                term_display = term[:50] + "..." if len(term) > 50 else term
                click.echo(f"    {term_display} → {translation}")
            if len(items) > 5:
                click.echo(f"    ... and {len(items) - 5} more")
    else:
        click.echo("\n(Migration loads translations dynamically)")


def get_commands():
    """Return CLI commands for this extension."""
    return [gdi_userportal]
