# SPDX-FileCopyrightText: 2026 Stichting Health-RI
#
# SPDX-License-Identifier: Apache-2.0

"""Datasets that belong to a metadata profile the deployment does not enable are hidden.

A harvest source names its profile with the ``metadata_profile`` key of its config. When that profile
is not among the enabled ones (``ckanext.dcat.metadata_profiles``), the datasets the source harvested
are valid for a model this deployment does not run: they stay in the database, untouched, and are left
out of the search (and so of every count), and a dataset page or ``package_show`` answers "not found" to
everyone but a sysadmin. Enable the profile again and they are back; nothing is reharvested or pruned.

A source without ``metadata_profile`` uses the main profile, which is always enabled, and a dataset
that no harvest source created is never hidden: there is nothing that says which profile it follows.
"""

from __future__ import annotations

import json
import re
from typing import Iterable, Optional

from ckanext.gdi_userportal.profile_packs.prune import SOURCE_METADATA_PROFILE_KEY, find_sources_with_retired_profile

ENABLED_PROFILES_OPTION = "ckanext.dcat.metadata_profiles"
SEARCH_FIELD = "harvest_source_id"


def enabled_profiles(raw) -> list:
    """The enabled profiles of the config option: a string split on whitespace and commas, or a list."""
    if raw is None:
        return []
    if isinstance(raw, str):
        return [name for name in re.split(r"[,\s]+", raw) if name]
    return [str(name).strip() for name in raw if str(name).strip()]


def hidden_source_ids(session, enabled: Iterable[str]) -> list:
    """The harvest sources whose profile is not enabled. Nothing is hidden when no profiles are configured."""
    enabled = list(enabled)
    if not enabled:
        return []
    return [source.source_id for source in find_sources_with_retired_profile(session, enabled)]


def package_source_id(session, package_id) -> Optional[str]:
    """The harvest source that created the dataset, from its current harvest object, or None."""
    from sqlalchemy import inspect, text

    if not package_id or not inspect(session.get_bind()).has_table("harvest_object"):
        return None
    return session.execute(
        text("SELECT harvest_source_id FROM harvest_object WHERE package_id = :id AND current ORDER BY gathered DESC LIMIT 1"),
        {"id": package_id},
    ).scalar()


def source_profiles(session, source_ids: Iterable[str]) -> dict:
    """``{source id: the metadata_profile its config names, or None}`` for the harvest sources that exist.

    A source that names no profile, or whose config is not JSON, maps to None: it follows the main profile.
    A source that does not exist, or a deployment without ckanext-harvest, is simply absent from the answer.
    """
    from sqlalchemy import bindparam, inspect, text

    ids = sorted({source_id for source_id in source_ids if source_id})
    if not ids or not inspect(session.get_bind()).has_table("harvest_source"):
        return {}
    statement = text("SELECT id, config FROM harvest_source WHERE id IN :ids").bindparams(
        bindparam("ids", expanding=True)
    )
    return {source_id: _named_profile(config) for source_id, config in session.execute(statement, {"ids": ids})}


def _named_profile(config) -> Optional[str]:
    try:
        parsed = json.loads(config) if config else {}
    except ValueError:
        return None
    profile = parsed.get(SOURCE_METADATA_PROFILE_KEY) if isinstance(parsed, dict) else None
    return profile.strip() if isinstance(profile, str) and profile.strip() else None


def is_hidden(session, enabled: Iterable[str], package_id) -> bool:
    hidden = hidden_source_ids(session, enabled)
    return bool(hidden) and package_source_id(session, package_id) in hidden


def search_exclusion(source_ids: Iterable[str]) -> Optional[str]:
    """The Solr filter query that leaves out the datasets of these sources, None when there are none."""
    quoted = " OR ".join(f'"{source_id}"' for source_id in source_ids)
    return f"-{SEARCH_FIELD}:({quoted})" if quoted else None


def hide_from_search(search_params: dict, session, enabled: Iterable[str]) -> dict:
    """``search_params`` with the datasets of sources of a profile that is not enabled filtered out."""
    exclusion = search_exclusion(hidden_source_ids(session, enabled))
    if exclusion:
        search_params["fq_list"] = [*(search_params.get("fq_list") or []), exclusion]
    return search_params
