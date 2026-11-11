# SPDX-FileCopyrightText: 2026 Stichting Health-RI
#
# SPDX-License-Identifier: Apache-2.0

"""
The empty values that datasets already have in the database (``blank_values.py``: new saves leave them out).

Plain SQL on a SQLAlchemy session, so it works on SQLite and PostgreSQL; nothing is committed here, the caller
owns the transaction. Only the extras of fields the dataset schema names are looked at: an extra that is empty
is removed, one that holds some empty parts (``{"en": "Title", "nl": ""}``) is rewritten without them.
"""

import dataclasses
import json
from typing import Any, Callable, Collection, List, Optional, Tuple

from sqlalchemy import text

from ckanext.gdi_userportal.blank_values import prune

EXTRA = "extra"
RESOURCE = "resource"

# a dataset type -> (the names of its dataset fields, the names of its resource fields)
FieldNames = Callable[[Optional[str]], Tuple[Collection[str], Collection[str]]]


@dataclasses.dataclass(frozen=True)
class Change:
    """One stored value that holds empty parts: ``after`` is None when the whole value is to be removed."""

    kind: str  # EXTRA (a row of package_extra) or RESOURCE (a key in the extras of a resource)
    row_id: str
    package_id: str
    package_name: str
    key: str
    before: Any  # as it is stored: a text in package_extra, a text or a list or object in the extras of a resource
    after: Any


def _changed(value: Any, names: Collection[str], key: str) -> Tuple[bool, Any]:
    """Whether the value of a schema field holds empty parts, and what it is without them (the same type)."""
    if key not in names:
        return False, None
    after = prune(value)
    return after != value, after


def _shown(value: Any) -> str:
    return value if isinstance(value, str) else json.dumps(value)


def _extra_changes(session, field_names: FieldNames) -> List[Change]:
    rows = session.execute(
        text(
            "SELECT e.id, e.package_id, p.name, p.type, e.key, e.value FROM package_extra e "
            "JOIN package p ON p.id = e.package_id WHERE e.state = 'active' ORDER BY p.name, e.key"
        )
    ).fetchall()
    changes = []
    for row_id, package_id, name, package_type, key, value in rows:
        value = "" if value is None else value
        different, after = _changed(value, field_names(package_type)[0], key)
        if different:
            changes.append(Change(EXTRA, row_id, package_id, name, key, value, after))
    return changes


def _stored_extras(raw) -> dict:
    """The extras of a resource: a JSON text, or already an object; nothing when it is neither."""
    try:
        stored = json.loads(raw) if isinstance(raw, str) else raw
    except ValueError:
        return {}
    return dict(stored) if isinstance(stored, dict) else {}


def _resource_changes(session, field_names: FieldNames) -> List[Change]:
    rows = session.execute(
        text(
            "SELECT r.id, r.package_id, p.name, p.type, r.extras FROM resource r "
            "JOIN package p ON p.id = r.package_id WHERE r.state = 'active' AND r.extras IS NOT NULL "
            "ORDER BY p.name, r.position"
        )
    ).fetchall()
    changes = []
    for row_id, package_id, name, package_type, raw in rows:
        names = field_names(package_type)[1]
        for key, value in _stored_extras(raw).items():
            different, after = _changed(value, names, key)
            if different:
                changes.append(Change(RESOURCE, row_id, package_id, name, key, value, after))
    return changes


def find_changes(session, field_names: FieldNames) -> List[Change]:
    """The values of active datasets and resources that hold empty parts."""
    return _extra_changes(session, field_names) + _resource_changes(session, field_names)


def apply_changes(session, changes: List[Change]) -> int:
    """Remove or rewrite the values. Returns the number of values changed."""
    resources = {}
    for change in changes:
        if change.kind == EXTRA:
            if change.after is None:
                session.execute(text("DELETE FROM package_extra WHERE id = :id"), {"id": change.row_id})
            else:
                session.execute(
                    text("UPDATE package_extra SET value = :value WHERE id = :id"),
                    {"value": change.after, "id": change.row_id},
                )
        else:
            resources.setdefault(change.row_id, []).append(change)
    for row_id, resource_changes in resources.items():
        raw = session.execute(text("SELECT extras FROM resource WHERE id = :id"), {"id": row_id}).scalar()
        stored = _stored_extras(raw)
        for change in resource_changes:
            if change.after is None:
                stored.pop(change.key, None)
            else:
                stored[change.key] = change.after
        session.execute(
            text("UPDATE resource SET extras = :extras WHERE id = :id"),
            {"extras": json.dumps(stored), "id": row_id},
        )
    return len(changes)


def format_report(changes: List[Change], deleting: bool) -> List[str]:
    """The report lines: what is removed and what is rewritten, per dataset."""
    if not changes:
        return ["No empty values are stored."]
    removed = sum(1 for change in changes if change.after is None)
    lines = [
        "%s %d empty value(s) and %d value(s) with empty parts, in %d dataset(s):"
        % ("Removing" if deleting else "Would remove", removed, len(changes) - removed, len({c.package_id for c in changes}))
    ]
    current = None
    for change in changes:
        if change.package_name != current:
            current = change.package_name
            lines.append(current)
        what = "remove" if change.after is None else "rewrite"
        scope = "resource " if change.kind == RESOURCE else ""
        lines.append("  %s%s: %s %s" % (scope, change.key, what, _shown(change.before)[:60]))
    if not deleting:
        lines.append("A dry run: nothing was changed. Use --apply to change it.")
    return lines
