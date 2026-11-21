# SPDX-FileCopyrightText: 2026 Stichting Health-RI
#
# SPDX-License-Identifier: Apache-2.0

"""
The extras a retired metadata profile leaves behind (ADR 0001, section 7).

Retiring a profile means removing it from ``GDI_METADATA_PROFILES`` and regenerating. The
datasets keep the values they had saved for that profile's fields, as extras that no schema
describes any more. They are harmless, and this finds them and, on request, removes them.

Nothing here decides which extras are orphaned: ``generator.retired_fields`` does, and its
answer is passed in. These functions take a SQLAlchemy session and use plain SQL, so they work on
SQLite and PostgreSQL. They never commit: the caller owns the transaction.

Only whole dataset extras are removed. A subfield a retired profile added to a shared field
(for example the opening hours of a contact point) stays inside that field's value.
"""

from __future__ import annotations

import dataclasses
import json

from sqlalchemy import bindparam, inspect, text

# The harvest source config key that names a metadata profile (ckanext.dcat.metadata_profiles).
SOURCE_METADATA_PROFILE_KEY = "metadata_profile"


@dataclasses.dataclass(frozen=True)
class Orphan:
    """A dataset and the extras on it that belong to retired profiles."""

    package_id: str
    name: str
    state: str
    private: bool
    keys: tuple


@dataclasses.dataclass(frozen=True)
class RetiredSource:
    """A harvest source whose ``metadata_profile`` is not enabled; its jobs fail until it is edited."""

    source_id: str
    title: str
    active: bool
    profile: str


def find_orphaned_extras(session, keys, package_type="dataset"):
    """The datasets of ``package_type`` that carry any of the extras ``keys``, by name.

    Deleted datasets are included: their extras are as orphaned, and a restored dataset would
    bring them back.
    """
    if not keys:
        return []
    statement = text(
        "SELECT p.id, p.name, p.state, p.private, e.key "
        "FROM package_extra e JOIN package p ON p.id = e.package_id "
        "WHERE p.type = :package_type AND e.key IN :keys "
        "ORDER BY p.name, e.key"
    ).bindparams(bindparam("keys", expanding=True))
    grouped = {}
    for package_id, name, state, private, key in session.execute(
        statement, {"package_type": package_type, "keys": sorted(keys)}
    ):
        grouped.setdefault((package_id, name, state, bool(private)), []).append(key)
    return [Orphan(*identity, tuple(found)) for identity, found in grouped.items()]


def delete_orphaned_extras(session, orphans):
    """Delete the listed extras and return how many rows went. Does not commit."""
    statement = text("DELETE FROM package_extra WHERE package_id = :package_id AND key IN :keys").bindparams(
        bindparam("keys", expanding=True)
    )
    deleted = 0
    for orphan in orphans:
        result = session.execute(statement, {"package_id": orphan.package_id, "keys": list(orphan.keys)})
        deleted += result.rowcount
    return deleted


def find_sources_with_retired_profile(session, enabled):
    """The harvest sources that name a ``metadata_profile`` outside ``enabled``.

    A deployment without ckanext-harvest has none. A source whose config is not JSON is skipped:
    it cannot name a profile.
    """
    if not inspect(session.get_bind()).has_table("harvest_source"):
        return []
    sources = []
    for source_id, title, active, config in session.execute(
        text("SELECT id, title, active, config FROM harvest_source ORDER BY title, id")
    ):
        try:
            parsed = json.loads(config) if config else {}
        except ValueError:
            continue
        profile = parsed.get(SOURCE_METADATA_PROFILE_KEY) if isinstance(parsed, dict) else None
        if isinstance(profile, str) and profile.strip() and profile.strip() not in enabled:
            sources.append(RetiredSource(source_id, title or "", bool(active), profile.strip()))
    return sources


def format_report(enabled, retired, orphans, sources, deleting):
    """The report the prune command prints, as lines. Keys only: values are never shown."""
    lines = [f"Enabled metadata profiles: {', '.join(enabled)}"]

    dataset_fields = retired.get("dataset_fields", {})
    if dataset_fields:
        lines.append("Dataset fields that only retired profiles define:")
        lines += [f"  {field} ({', '.join(packs)})" for field, packs in sorted(dataset_fields.items())]
    else:
        lines.append("No retired profile defines a dataset field: nothing can be orphaned.")
    if retired.get("resource_fields"):
        lines.append(
            "Resource fields of retired profiles are not pruned by this command: "
            + ", ".join(sorted(retired["resource_fields"]))
        )

    extras = sum(len(orphan.keys) for orphan in orphans)
    lines.append(f"Orphaned extras: {extras} on {len(orphans)} dataset(s)")
    for orphan in orphans:
        flags = ", ".join(flag for flag in (orphan.state, "private" if orphan.private else "") if flag)
        lines.append(f"  {orphan.name} ({orphan.package_id}) [{flags}]: {', '.join(orphan.keys)}")

    if sources:
        lines.append(
            f"Harvest sources naming a profile that is not enabled: {len(sources)} "
            "(their jobs fail until the source is edited; this command does not change them)"
        )
        lines += [
            f"  {source.title or source.source_id} ({source.source_id}) "
            f"[{'active' if source.active else 'inactive'}]: {source.profile}"
            for source in sources
        ]

    if not deleting:
        lines.append(
            "Dry run: nothing was changed." + (" Rerun with --delete to remove these extras." if orphans else "")
        )
    return lines
